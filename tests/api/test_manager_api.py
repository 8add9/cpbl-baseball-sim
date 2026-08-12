from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from baseball_sim.api import create_app
from baseball_sim.api.career_repository import SqliteCareerRepository
from baseball_sim.api.manager_repository import (
    ManagerCorruptError,
    SqliteManagerRepository,
)
from baseball_sim.api.repository import InMemoryGameRepository

ARTIFACT_ROOT = Path("artifacts/generated/ratings")

pytestmark = pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for Manager API integration",
)


def _client(database: Path) -> TestClient:
    return TestClient(
        create_app(
            InMemoryGameRepository(),
            SqliteCareerRepository(database.with_name("careers.sqlite3")),
            SqliteManagerRepository(database, ARTIFACT_ROOT),
        )
    )


def _create(client: TestClient, operation_id: str = "manager-create") -> dict[str, object]:
    response = client.post(
        "/api/managers",
        json={"expected_revision": 0, "operation_id": operation_id, "seed": 42},
    )
    assert response.status_code == 201
    return response.json()


def _mutation(view: dict[str, object], operation_id: str) -> dict[str, object]:
    return {"expected_revision": view["revision"], "operation_id": operation_id}


def test_player_catalog_endpoints_are_paginated_and_lookup_canonical_cards(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "managers.sqlite3")
    listed = client.get("/api/players?limit=2")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 5160
    assert len(payload["players"]) == 2
    card = payload["players"][0]
    assert set(card) == {
        "player_id", "source_player_id", "name", "season_year", "team", "kind",
        "profile_positions", "role", "incomplete_season", "abilities",
    }
    detail = client.get(f"/api/players/{card['player_id']}")
    assert detail.status_code == 200
    assert detail.json() == card
    assert client.get("/api/players/missing-card").status_code == 404


def test_manager_api_create_unique_league_idempotency_round_restart_and_compact_save(
    tmp_path: Path,
) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    created = _create(client)
    manager_id = created["manager_id"]
    assert created["revision"] == 1
    assert created["games_completed"] == 0
    assert created["total_games"] == 360
    assert len(created["teams"]) == len(created["standings"]) == 6
    assert [team["strategy"] for team in created["teams"]] == [
        "balanced",
        "offense",
        "pitching",
        "balanced",
        "offense",
        "pitching",
    ]
    card_ids = [
        card["card_id"]
        for team in created["teams"]
        for card in team["lineup"]
    ]
    assert len(card_ids) == len(set(card_ids)) == 54
    assert len(created["catalog_fingerprint"]) == 64

    assert _create(client) == created
    listed = client.get("/api/managers")
    assert listed.status_code == 200
    assert [item["manager_id"] for item in listed.json()["managers"]] == [manager_id]

    request = _mutation(created, "next-game")
    first = client.post(
        f"/api/managers/{manager_id}/simulate-next-game", json=request
    )
    assert first.status_code == 200
    view = first.json()
    assert view["revision"] == 2
    assert view["games_completed"] == 1
    assert len(view["recent_results"]) == 1
    duplicate = client.post(
        f"/api/managers/{manager_id}/simulate-next-game", json=request
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == view

    stale = client.post(
        f"/api/managers/{manager_id}/simulate-round",
        json={"expected_revision": 1, "operation_id": "stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"

    round_response = client.post(
        f"/api/managers/{manager_id}/simulate-round",
        json=_mutation(view, "round"),
    )
    assert round_response.status_code == 200
    view = round_response.json()
    assert view["games_completed"] == 3
    assert view["next_game"]["round_number"] == 2

    restarted = _client(database)
    loaded = restarted.get(f"/api/managers/{manager_id}")
    assert loaded.status_code == 200
    assert loaded.json() == view

    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT state_json FROM manager_leagues WHERE manager_id=?", (manager_id,)
        ).fetchone()[0]
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(manager_operations)")
        }
    payload = json.loads(raw)
    assert payload["catalog_fingerprint"] == view["catalog_fingerprint"]
    assert "abilities" not in raw and "RatingRaw" not in raw
    assert "state_json" not in columns


def test_season_completion_rolls_back_invalid_mutation_and_list_skips_corrupt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    view = _create(client, "season-create")
    manager_id = view["manager_id"]
    response = client.post(
        f"/api/managers/{manager_id}/simulate-season",
        json=_mutation(view, "season"),
    )
    assert response.status_code == 200
    finished = response.json()
    assert finished["games_completed"] == 360
    assert finished["finished"] is True
    assert finished["next_game"] is None
    assert sum(row["wins"] for row in finished["standings"]) == 360
    assert sum(row["losses"] for row in finished["standings"]) == 360

    advanced_response = client.post(
        f"/api/managers/{manager_id}/advance-season",
        json=_mutation(finished, "advance-season"),
    )
    assert advanced_response.status_code == 200
    advanced = advanced_response.json()
    assert advanced["season_year"] == finished["season_year"] + 1
    assert advanced["games_completed"] == 0
    assert advanced["finished"] is False

    rejected = client.post(
        f"/api/managers/{manager_id}/simulate-next-game",
        json={"expected_revision": finished["revision"], "operation_id": "stale-after-season"},
    )
    assert rejected.status_code == 409
    current = client.get(f"/api/managers/{manager_id}").json()
    assert current == advanced

    corrupt_id = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO manager_leagues VALUES (?, ?, ?, ?, ?)",
            (corrupt_id, 1, "not-json", "9999-01-01T00:00:00Z", "manager-sqlite-v1"),
        )
    corrupt = client.get(f"/api/managers/{corrupt_id}")
    assert corrupt.status_code == 409
    assert corrupt.json()["code"] == "manager_corrupt"
    listed = client.get("/api/managers").json()["managers"]
    assert [item["manager_id"] for item in listed] == [manager_id]

    invalid = client.get("/api/managers/not-a-uuid")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "manager_invalid"


def test_repository_fails_closed_when_configured_artifact_root_is_invalid(
    tmp_path: Path,
) -> None:
    with pytest.raises(ManagerCorruptError, match="artifact"):
        SqliteManagerRepository(tmp_path / "manager.sqlite3", tmp_path / "missing")


def test_preseason_roster_builder_rejects_star_overload_accepts_legal_swap_and_locks(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "managers.sqlite3")
    view = _create(client, "builder-create")
    team = view["teams"][0]
    outgoing = team["lineup"][0]
    candidates_response = client.get(
        f"/api/managers/{view['manager_id']}/roster-candidates",
        params={"team_id": team["team_id"], "outgoing_card_id": outgoing["card_id"]},
    )
    assert candidates_response.status_code == 200
    candidates = candidates_response.json()["candidates"]
    assert {candidate["tier"] for candidate in candidates} >= {"SSR", "R"}

    star = next(candidate for candidate in candidates if candidate["tier"] == "SSR")
    rejected = client.post(
        f"/api/managers/{view['manager_id']}/replace-card",
        json={
            **_mutation(view, "builder-star-overload"),
            "team_id": team["team_id"],
            "outgoing_card_id": outgoing["card_id"],
            "incoming_card_id": star["card_id"],
        },
    )
    assert rejected.status_code == 422
    assert "budget" in rejected.json()["message"] or "SSR" in rejected.json()["message"]
    assert client.get(f"/api/managers/{view['manager_id']}").json() == view

    regular = next(candidate for candidate in candidates if candidate["tier"] == "R")
    accepted = client.post(
        f"/api/managers/{view['manager_id']}/replace-card",
        json={
            **_mutation(view, "builder-legal-swap"),
            "team_id": team["team_id"],
            "outgoing_card_id": outgoing["card_id"],
            "incoming_card_id": regular["card_id"],
        },
    )
    assert accepted.status_code == 200
    changed = accepted.json()
    assert changed["revision"] == 2
    assert changed["teams"][0]["strategy"] == "custom"
    assert changed["teams"][0]["lineup"][0]["card_id"] == regular["card_id"]

    played = client.post(
        f"/api/managers/{view['manager_id']}/simulate-next-game",
        json=_mutation(changed, "builder-play"),
    ).json()
    locked = client.post(
        f"/api/managers/{view['manager_id']}/replace-card",
        json={
            **_mutation(played, "builder-locked"),
            "team_id": team["team_id"],
            "outgoing_card_id": regular["card_id"],
            "incoming_card_id": outgoing["card_id"],
        },
    )
    assert locked.status_code == 422
    assert "locked" in locked.json()["message"]


def test_team_8add9_unlocks_caps_and_rotation_allows_same_starter(
    tmp_path: Path,
) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    view = _create(client, "custom-create")
    manager_id = view["manager_id"]
    user_team = next(
        team for team in view["teams"] if team["team_id"] == view["user_team_id"]
    )

    renamed_response = client.post(
        f"/api/managers/{manager_id}/rename-team",
        json={**_mutation(view, "rename-8add9"), "name": "8add9"},
    )
    assert renamed_response.status_code == 200
    renamed = renamed_response.json()
    renamed_team = next(
        team
        for team in renamed["teams"]
        if team["team_id"] == renamed["user_team_id"]
    )
    assert renamed_team["name"] == "8add9"
    assert renamed_team["unlimited_roster"] is True
    assert renamed_team["cost_limit"] is None
    assert renamed_team["ssr_limit"] is None

    starter = user_team["rotation"][0]["card_id"]
    rotation_response = client.post(
        f"/api/managers/{manager_id}/rotation-plan",
        json={
            **_mutation(renamed, "same-starter"),
            "starter_card_ids": [starter] * 4,
        },
    )
    assert rotation_response.status_code == 200
    rotated = rotation_response.json()
    rotated_team = next(
        team
        for team in rotated["teams"]
        if team["team_id"] == rotated["user_team_id"]
    )
    assert rotated_team["rotation_plan"] == [starter] * 4
    assert rotated_team["next_starter_card_id"] == starter

    restarted = _client(database)
    assert restarted.get(f"/api/managers/{manager_id}").json() == rotated
