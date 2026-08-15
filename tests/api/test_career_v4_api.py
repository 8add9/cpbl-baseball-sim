from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from baseball_sim.api.app import create_app
from baseball_sim.api.career_repository import SqliteCareerRepository
from baseball_sim.api.repository import InMemoryGameRepository
from baseball_sim.career.persistence_v4 import SqliteCareerV4Repository


def _app(database: Path) -> TestClient:
    legacy = SqliteCareerRepository(database)
    return TestClient(
        create_app(
            InMemoryGameRepository(),
            legacy,
            career_v4_repository=SqliteCareerV4Repository(database),
        )
    )


def _create_payload(operation_id: str = "v4-create") -> dict[str, object]:
    return {
        "expected_revision": 0,
        "operation_id": operation_id,
        "name": "新秀",
        "position": "CF",
        "bats": "left",
        "throws": "right",
        "archetype": "contact",
        "season_year": 2026,
        "seed": 42,
        "team_id": "A",
        "opponent_ids": ["B", "C", "D", "E", "F"],
    }


def test_create_plan_advance_dashboard_restart_and_idempotency(tmp_path) -> None:
    database = tmp_path / "careers.sqlite3"
    client = _app(database)
    created_response = client.post("/api/careers-v4", json=_create_payload())
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["phase"] == "week_planning"
    assert created["migrated_from_schema"] is None
    career_id = created["career_id"]
    plan_request = {"expected_revision": 1, "operation_id": "plan", "actions": []}
    planned_response = client.post(
        f"/api/careers-v4/{career_id}/plan-week", json=plan_request
    )
    assert planned_response.status_code == 200
    advanced_request = {"expected_revision": 2, "operation_id": "day-1"}
    advanced_response = client.post(
        f"/api/careers-v4/{career_id}/advance-day", json=advanced_request
    )
    assert advanced_response.status_code == 200
    advanced = advanced_response.json()
    assert advanced["revision"] == 3
    assert _app(database).get(
        f"/api/careers-v4/{career_id}/dashboard"
    ).json() == advanced
    assert client.post(
        f"/api/careers-v4/{career_id}/advance-day", json=advanced_request
    ).json() == advanced
    stale = client.post(
        f"/api/careers-v4/{career_id}/advance-day",
        json={"expected_revision": 2, "operation_id": "stale"},
    )
    assert stale.status_code == 409


def test_existing_v3_save_migrates_and_survives_restart(tmp_path) -> None:
    database = tmp_path / "careers.sqlite3"
    client = _app(database)
    legacy_payload = _create_payload("legacy-create")
    legacy_payload.pop("team_id")
    legacy_payload.pop("opponent_ids")
    legacy_payload["season_games"] = 120
    legacy = client.post("/api/careers", json=legacy_payload)
    assert legacy.status_code == 201
    career_id = legacy.json()["career_id"]
    migrated = client.post(
        f"/api/careers-v4/{career_id}/migrate-v3",
        json={
            "expected_revision": 0,
            "operation_id": "migrate",
            "team_id": "A",
            "opponent_ids": ["B", "C", "D", "E", "F"],
        },
    )
    assert migrated.status_code == 201
    body = migrated.json()
    assert body["migrated_from_schema"] == 3
    assert _app(database).get(
        f"/api/careers-v4/{career_id}/dashboard"
    ).json() == body


def test_two_complete_seasons_require_the_full_offseason_flow(tmp_path) -> None:
    database = tmp_path / "two-seasons.sqlite3"
    client = _app(database)
    career = client.post("/api/careers-v4", json=_create_payload("two-create")).json()
    career_id = career["career_id"]
    for season in range(2):
        planned = client.post(
            f"/api/careers-v4/{career_id}/plan-week",
            json={
                "expected_revision": career["revision"],
                "operation_id": f"plan-{season}",
                "actions": [],
            },
        )
        assert planned.status_code == 200
        career = planned.json()
        finished = client.post(
            f"/api/careers-v4/{career_id}/simulate-season",
            json={
                "expected_revision": career["revision"],
                "operation_id": f"season-{season}",
            },
        )
        assert finished.status_code == 200
        career = finished.json()
        assert career["games_played"] == 120
        assert career["phase"] == "season_review"
        for step in range(5):
            transition = client.post(
                f"/api/careers-v4/{career_id}/advance-phase",
                json={
                    "expected_revision": career["revision"],
                    "operation_id": f"offseason-{season}-{step}",
                },
            )
            assert transition.status_code == 200
            career = transition.json()
        assert career["season_year"] == 2027 + season
        assert career["completed_seasons"] == season + 1
        assert career["games_played"] == 0
        assert career["phase"] == "week_planning"
        restarted = _app(database).get(
            f"/api/careers-v4/{career_id}/dashboard"
        )
        assert restarted.status_code == 200
        assert restarted.json() == career


def test_interactive_game_accepts_pa_strategy_and_persists_extended_stats(tmp_path) -> None:
    database = tmp_path / "interactive.sqlite3"
    client = _app(database)
    career = client.post("/api/careers-v4", json=_create_payload("interactive-create")).json()
    career_id = career["career_id"]
    career = client.post(
        f"/api/careers-v4/{career_id}/plan-week",
        json={
            "expected_revision": career["revision"],
            "operation_id": "interactive-plan",
            "actions": [],
        },
    ).json()
    while not career["calendar_days"][career["weekday"] - 1]["is_game_day"]:
        career = client.post(
            f"/api/careers-v4/{career_id}/advance-day",
            json={
                "expected_revision": career["revision"],
                "operation_id": f"skip-{career['weekday']}",
            },
        ).json()
    entered = client.post(
        f"/api/careers-v4/{career_id}/play-game",
        json={"expected_revision": career["revision"], "operation_id": "enter-game"},
    )
    assert entered.status_code == 200
    career = entered.json()
    assert career["phase"] == "player_pa"
    assert career["active_game"] is not None
    resolved = client.post(
        f"/api/careers-v4/{career_id}/resolve-pa",
        json={
            "expected_revision": career["revision"],
            "operation_id": "selected-pa",
            "approach": "power_swing",
            "baserunning": "aggressive",
        },
    )
    assert resolved.status_code == 200
    career = resolved.json()
    assert career["phase"] in {"player_pa", "post_game"}
    assert career["season_stats"]["stolen_bases"] >= 0
    assert career["season_stats"]["caught_stealing"] >= 0
    restarted = _app(database).get(f"/api/careers-v4/{career_id}/dashboard")
    assert restarted.json() == career
