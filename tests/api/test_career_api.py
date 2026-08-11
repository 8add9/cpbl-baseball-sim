from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from baseball_sim.api import create_app
from baseball_sim.api.career_repository import SqliteCareerRepository
from baseball_sim.api.repository import InMemoryGameRepository


def _app(path: Path) -> TestClient:
    return TestClient(
        create_app(InMemoryGameRepository(), SqliteCareerRepository(path))
    )


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "careers.sqlite3"


@pytest.fixture
def client(database: Path) -> TestClient:
    return _app(database)


def _create(
    client: TestClient,
    *,
    operation_id: str = "create-1",
    season_games: int = 24,
) -> dict[str, object]:
    response = client.post(
        "/api/careers",
        json={
            "expected_revision": 0,
            "operation_id": operation_id,
            "name": "測試新人",
            "position": "OF",
            "bats": "left",
            "throws": "right",
            "archetype": "balanced",
            "season_year": 2026,
            "seed": 42,
            "season_games": season_games,
        },
    )
    assert response.status_code == 201
    return response.json()


def _mutation(view: dict[str, object], operation_id: str) -> dict[str, object]:
    return {"expected_revision": view["revision"], "operation_id": operation_id}


def test_create_list_get_and_process_restart_reload(
    client: TestClient, database: Path
) -> None:
    created = _create(client)
    assert created["revision"] == 1
    assert created["age"] == 18
    assert created["games_played"] == 0
    assert created["experience"] == 0
    assert created["development_points"] == 0
    assert created["retired"] is False
    assert created["persistence_version"] == "career-sqlite-v1"
    assert created["schema_version"] == 3
    assert created["model_version"] == "batter-career-v0.3"
    assert created["skills"]["contact"]["score"] == pytest.approx(-0.6)
    assert created["skills"]["contact"]["potential_score"] == pytest.approx(5.5)
    assert created["skills"]["contact"]["next_cost"] == 1
    assert created["skills"]["contact"]["can_train"] is False
    assert created["skills"]["speed_proxy"]["next_cost"] is None
    assert created["skills"]["speed_proxy"]["can_train"] is False

    listed = client.get("/api/careers")
    assert listed.status_code == 200
    assert [item["career_id"] for item in listed.json()["careers"]] == [
        created["career_id"]
    ]

    restarted = _app(database)
    loaded = restarted.get(f"/api/careers/{created['career_id']}")
    assert loaded.status_code == 200
    assert loaded.json() == created


def test_create_is_idempotent_and_payload_mismatch_conflicts(client: TestClient) -> None:
    first = _create(client, operation_id="same-create")
    duplicate = _create(client, operation_id="same-create")
    assert duplicate == first

    mismatch = client.post(
        "/api/careers",
        json={
            "expected_revision": 0,
            "operation_id": "same-create",
            "name": "不同名字",
            "position": "OF",
            "bats": "left",
            "throws": "right",
            "archetype": "balanced",
            "season_year": 2026,
            "seed": 42,
            "season_games": 24,
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "operation_conflict"


def test_game_month_season_controls_and_recent_results(client: TestClient) -> None:
    view = _create(client, season_games=22)
    career_id = view["career_id"]

    game = client.post(
        f"/api/careers/{career_id}/simulate-game",
        json={**_mutation(view, "game-1"), "plate_appearances": 5},
    )
    assert game.status_code == 200
    view = game.json()
    assert view["revision"] == 2
    assert view["games_played"] == 1
    assert view["experience"] == view["season_stats"]["pa"]
    assert view["experience"] >= 3
    assert len(view["recent_results"]) == 1
    assert view["recent_results"][0]["xp_earned"] == view["season_stats"]["pa"]

    month = client.post(
        f"/api/careers/{career_id}/simulate-month",
        json={**_mutation(view, "month-1"), "games": 20, "plate_appearances": 4},
    )
    assert month.status_code == 200
    view = month.json()
    assert view["games_played"] == 21
    assert len(view["recent_results"]) == 10

    remainder = client.post(
        f"/api/careers/{career_id}/simulate-month",
        json={**_mutation(view, "month-2"), "games": 20},
    )
    assert remainder.status_code == 200
    view = remainder.json()
    assert view["games_played"] == 22

    season = client.post(
        f"/api/careers/{career_id}/simulate-season",
        json={**_mutation(view, "season-1"), "plate_appearances": 4},
    )
    assert season.status_code == 200
    view = season.json()
    assert view["age"] == 19
    assert view["season_year"] == 2027
    assert view["games_played"] == 0
    assert view["season_stats"]["games"] == 0
    assert view["career_stats"]["games"] == 22


def test_training_uses_dp_and_returns_score_raw_display_potential_cost(
    client: TestClient,
) -> None:
    view = _create(client, season_games=20)
    career_id = view["career_id"]
    simulated = client.post(
        f"/api/careers/{career_id}/simulate-month",
        json={**_mutation(view, "earn-dp"), "games": 15, "plate_appearances": 4},
    )
    assert simulated.status_code == 200
    view = simulated.json()
    assert view["experience"] >= 60
    assert view["development_points"] == 1
    assert view["skills"]["contact"]["can_train"] is True
    old = view["skills"]["contact"]

    trained = client.post(
        f"/api/careers/{career_id}/train",
        json={**_mutation(view, "train-1"), "skill": "contact", "purchases": 1},
    )
    assert trained.status_code == 200
    view = trained.json()
    skill = view["skills"]["contact"]
    assert skill["score"] == pytest.approx(old["score"] + 0.1)
    assert skill["rating_raw"] > old["rating_raw"]
    assert isinstance(skill["rating_display"], int)
    assert skill["potential_score"] == old["potential_score"]
    assert view["development_points"] == 0
    assert view["season_purchases"] == 1

    speed = client.post(
        f"/api/careers/{career_id}/train",
        json={**_mutation(view, "train-speed"), "skill": "speed_proxy"},
    )
    assert speed.status_code == 422
    assert "read-only" in speed.json()["message"]


def test_twenty_games_train_and_reload_preserves_revision_and_score(
    client: TestClient, database: Path
) -> None:
    view = _create(client, operation_id="integration-create", season_games=24)
    career_id = view["career_id"]
    response = client.post(
        f"/api/careers/{career_id}/simulate-month",
        json={**_mutation(view, "integration-games"), "games": 20},
    )
    assert response.status_code == 200
    view = response.json()
    assert view["games_played"] == 20
    assert view["experience"] >= 60
    old_score = view["skills"]["contact"]["score"]
    response = client.post(
        f"/api/careers/{career_id}/train",
        json={**_mutation(view, "integration-train"), "skill": "contact"},
    )
    assert response.status_code == 200
    trained = response.json()
    assert trained["skills"]["contact"]["score"] == pytest.approx(old_score + 0.1)

    loaded = _app(database).get(f"/api/careers/{career_id}")
    assert loaded.status_code == 200
    assert loaded.json() == trained


def test_partial_pa_restart_is_exact_and_quick_game_finishes_it(
    client: TestClient, database: Path
) -> None:
    view = _create(client, operation_id="partial-create")
    career_id = view["career_id"]
    response = client.post(
        f"/api/careers/{career_id}/next-pa",
        json=_mutation(view, "partial-pa"),
    )
    assert response.status_code == 200
    partial = response.json()
    assert partial["games_played"] == 0
    assert partial["experience"] == 1
    assert partial["active_game"]["career_plate_appearances"] == 1
    assert partial["active_game"]["game_plate_appearances"] == 1
    assert partial["active_game"]["inning"] == 1
    assert partial["active_game"]["half"] == "top"
    assert len(partial["active_game"]["away_lineup"]) == 9
    assert len(partial["active_game"]["home_lineup"]) == 9
    assert partial["skills"]["power"]["next_cost"] is not None
    assert partial["skills"]["power"]["can_train"] is False

    restarted = _app(database)
    assert restarted.get(f"/api/careers/{career_id}").json() == partial
    response = restarted.post(
        f"/api/careers/{career_id}/simulate-game",
        json=_mutation(partial, "finish-partial"),
    )
    assert response.status_code == 200
    finished = response.json()
    assert finished["games_played"] == 1
    assert finished["experience"] == finished["season_stats"]["pa"]
    assert finished["active_game"] is None


def test_week_and_next_event_controls(client: TestClient) -> None:
    view = _create(client, operation_id="controls-create", season_games=8)
    career_id = view["career_id"]
    first = client.post(
        f"/api/careers/{career_id}/simulate-to-next-event",
        json=_mutation(view, "first-event"),
    )
    assert first.status_code == 200
    view = first.json()
    assert view["games_played"] == 1
    assert view["active_game"] is None

    week = client.post(
        f"/api/careers/{career_id}/simulate-week",
        json={**_mutation(view, "week"), "games": 6},
    )
    assert week.status_code == 200
    view = week.json()
    assert view["games_played"] == 7
    assert view["active_game"] is None


def test_stale_revision_duplicate_operation_and_operation_reuse(client: TestClient) -> None:
    created = _create(client)
    career_id = created["career_id"]
    request = {**_mutation(created, "once"), "plate_appearances": 4}
    first = client.post(f"/api/careers/{career_id}/simulate-game", json=request)
    assert first.status_code == 200
    first_view = first.json()

    duplicate = client.post(f"/api/careers/{career_id}/simulate-game", json=request)
    assert duplicate.status_code == 200
    assert duplicate.json() == first_view
    current = client.get(f"/api/careers/{career_id}").json()
    assert current["games_played"] == 1
    assert current["revision"] == 2

    stale = client.post(
        f"/api/careers/{career_id}/simulate-game",
        json={**_mutation(created, "stale"), "plate_appearances": 4},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"

    reused = client.post(
        f"/api/careers/{career_id}/simulate-game",
        json={**_mutation(created, "once"), "plate_appearances": 5},
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "operation_conflict"


def test_invalid_id_missing_id_invalid_body_and_corrupt_save_are_structured(
    client: TestClient, database: Path
) -> None:
    invalid = client.get("/api/careers/not-a-uuid")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "career_invalid"

    missing = client.get(f"/api/careers/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "career_not_found"

    bad_request = client.post(
        "/api/careers",
        json={"expected_revision": 0, "operation_id": "../bad"},
    )
    assert bad_request.status_code == 422
    assert bad_request.json()["code"] == "invalid_request"

    created = _create(client, operation_id="corrupt-create")
    healthy = _create(client, operation_id="healthy-create")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE careers SET state_json=? WHERE career_id=?",
            ("not-json", created["career_id"]),
        )
    corrupt = client.get(f"/api/careers/{created['career_id']}")
    assert corrupt.status_code == 409
    assert corrupt.json()["code"] == "career_corrupt"
    listed = client.get("/api/careers")
    assert listed.status_code == 200
    assert [item["career_id"] for item in listed.json()["careers"]] == [
        healthy["career_id"]
    ]


def test_operation_ledger_is_compact_and_does_not_store_state_snapshots(
    client: TestClient, database: Path
) -> None:
    view = _create(client, operation_id="ledger-create")
    career_id = view["career_id"]
    for index in range(12):
        response = client.post(
            f"/api/careers/{career_id}/next-pa",
            json=_mutation(view, f"ledger-{index}"),
        )
        assert response.status_code == 200
        view = response.json()

    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(career_operations_v2)")
        }
        assert "result_state_json" not in columns
        operation_bytes = connection.execute(
            """SELECT SUM(
                   LENGTH(operation_id) + LENGTH(career_id) + LENGTH(action)
                   + LENGTH(request_hash) + LENGTH(result_autosaved_at)
                   + LENGTH(persistence_version)
               ) FROM career_operations_v2"""
        ).fetchone()[0]
    assert operation_bytes < 5_000


def test_openapi_includes_all_career_controls(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/careers",
        "/api/careers/{career_id}",
        "/api/careers/{career_id}/train",
        "/api/careers/{career_id}/next-pa",
        "/api/careers/{career_id}/simulate-game",
        "/api/careers/{career_id}/simulate-week",
        "/api/careers/{career_id}/simulate-to-next-event",
        "/api/careers/{career_id}/simulate-month",
        "/api/careers/{career_id}/simulate-season",
    }.issubset(paths)
