from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from baseball_sim.api import create_app
from baseball_sim.api.repository import GameEvent, InMemoryGameRepository, SimulationLimitError


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(InMemoryGameRepository()))


def _create(client: TestClient, seed: int = 42) -> dict[str, object]:
    response = client.post("/api/games", json={"seed": seed})
    assert response.status_code == 201
    return response.json()


def test_health_is_minimal_and_pages_cors_is_explicit(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "0.1.0", "database": "ok"}
    assert set(health.json()) == {"status", "version", "database"}

    preflight = client.options(
        "/api/games",
        headers={
            "Origin": "https://8add9.github.io",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://8add9.github.io"

    rejected = client.options(
        "/api/games",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_create_returns_explicit_neutral_game_view(client: TestClient) -> None:
    view = _create(client)
    assert set(view) == {
        "game_id", "model_version", "state", "batter_ratings", "pitcher_ratings", "events"
    }
    assert view["state"] == {
        "inning": 1,
        "half": "top",
        "outs": 0,
        "bases": {"first": None, "second": None, "third": None},
        "away_score": 0,
        "home_score": 0,
        "batting_team": "away",
        "batter": "A1",
        "pitcher": "HP",
        "finished": False,
        "winner": None,
        "seed": 42,
        "plate_appearances": 0,
        "away_lineup": [f"A{index}" for index in range(1, 10)],
        "home_lineup": [f"H{index}" for index in range(1, 10)],
    }
    assert view["batter_ratings"] == {"contact": 65.0, "power": 65.0, "eye": 65.0}
    assert view["pitcher_ratings"] == {
        "stuff": 65.0, "control": 65.0, "hr_suppression": 65.0
    }
    assert view["events"] == []


def test_get_and_next_pa_preserve_session_and_append_event(client: TestClient) -> None:
    created = _create(client)
    game_id = created["game_id"]
    response = client.post(f"/api/games/{game_id}/next-pa")
    assert response.status_code == 200
    advanced = response.json()
    assert advanced["game_id"] == game_id
    assert advanced["state"]["plate_appearances"] == 1
    assert len(advanced["events"]) == 1
    event = advanced["events"][0]
    assert set(event) == {
        "sequence", "outcome", "batter", "pitcher", "runs_scored", "inning", "half", "description"
    }
    assert event["batter"] == "A1"
    assert event["pitcher"] == "HP"
    assert event["inning"] == 1
    assert event["half"] == "top"
    assert client.get(f"/api/games/{game_id}").json() == advanced


def test_simulate_half_stops_after_current_half(client: TestClient) -> None:
    created = _create(client)
    response = client.post(f"/api/games/{created['game_id']}/simulate-half")
    assert response.status_code == 200
    view = response.json()
    assert view["state"]["half"] == "bottom"
    assert view["state"]["inning"] == 1
    assert view["state"]["outs"] == 0
    assert len(view["events"]) == view["state"]["plate_appearances"]


def test_simulate_full_finishes_and_rejects_more_pa(client: TestClient) -> None:
    created = _create(client)
    game_id = created["game_id"]
    response = client.post(f"/api/games/{game_id}/simulate-full")
    assert response.status_code == 200
    final = response.json()
    assert final["state"]["finished"] is True
    assert final["state"]["winner"] in {"away", "home"}
    rejected = client.post(f"/api/games/{game_id}/next-pa")
    assert rejected.status_code == 409
    assert rejected.json() == {
        "code": "game_finished", "message": "The game is already finished."
    }


def test_reset_restores_initial_state_and_can_replace_seed(client: TestClient) -> None:
    created = _create(client, seed=42)
    game_id = created["game_id"]
    client.post(f"/api/games/{game_id}/next-pa")
    reset = client.post(f"/api/games/{game_id}/reset", json={"seed": 99})
    assert reset.status_code == 200
    view = reset.json()
    assert view["game_id"] == game_id
    assert view["state"]["seed"] == 99
    assert view["state"]["plate_appearances"] == 0
    assert view["state"]["inning"] == 1
    assert view["state"]["half"] == "top"
    assert view["events"] == []

    client.post(f"/api/games/{game_id}/next-pa")
    default_reset = client.post(f"/api/games/{game_id}/reset")
    assert default_reset.status_code == 200
    assert default_reset.json()["state"]["seed"] == 42


def test_same_seed_produces_identical_full_game_except_id(client: TestClient) -> None:
    first = _create(client, 777)
    second = _create(client, 777)
    first_final = client.post(f"/api/games/{first['game_id']}/simulate-full").json()
    second_final = client.post(f"/api/games/{second['game_id']}/simulate-full").json()
    first_final.pop("game_id")
    second_final.pop("game_id")
    assert first_final == second_final


def test_missing_game_and_invalid_payload_have_clear_errors(client: TestClient) -> None:
    missing = client.get("/api/games/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["code"] == "game_not_found"

    invalid = client.post("/api/games", json={"seed": 1, "unexpected": True})
    assert invalid.status_code == 422
    assert invalid.json() == {
        "code": "invalid_request", "message": "Request validation failed."
    }


def test_openapi_exposes_all_phase_one_operations(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/games",
        "/api/games/{game_id}",
        "/api/games/{game_id}/next-pa",
        "/api/games/{game_id}/simulate-half",
        "/api/games/{game_id}/simulate-full",
        "/api/games/{game_id}/reset",
    }.issubset(paths)


def test_repository_snapshots_and_failed_batches_do_not_leak_partial_state() -> None:
    repository = InMemoryGameRepository()
    created = repository.create(42)
    created.events.append(  # Mutating the returned snapshot must not mutate the repository.
        GameEvent("SO", "A1", "HP", 0, 1, "top", "fixture")
    )
    assert repository.get(created.game_id).events == []

    with pytest.raises(SimulationLimitError):
        repository.simulate_full(created.game_id, max_pa=1)
    current = repository.get(created.game_id)
    assert current.state.plate_appearances == 0
    assert current.events == []
