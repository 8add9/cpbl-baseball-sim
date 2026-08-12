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
    assert view["player_stats"]
    assert {item["team_id"] for item in view["player_stats"]} == {
        created["next_game"]["away_team_id"],
        created["next_game"]["home_team_id"],
    }
    assert all(item["team_name"] for item in view["player_stats"])
    assert all(item["card_season_year"] <= 2025 for item in view["player_stats"])
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


def test_roster_builder_rejects_star_overload_and_accepts_legal_swap(
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
    reopened = client.post(
        f"/api/managers/{view['manager_id']}/replace-card",
        json={
            **_mutation(played, "builder-in-season"),
            "team_id": team["team_id"],
            "outgoing_card_id": regular["card_id"],
            "incoming_card_id": outgoing["card_id"],
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["games_completed"] == 1


def test_multiple_in_season_roster_swaps_survive_restart_and_continue(
    tmp_path: Path,
) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    view = _create(client, "multi-swap-create")
    manager_id = view["manager_id"]
    view = client.post(
        f"/api/managers/{manager_id}/rename-team",
        json={**_mutation(view, "multi-swap-unlimited"), "name": "8add9"},
    ).json()
    view = client.post(
        f"/api/managers/{manager_id}/simulate-next-game",
        json=_mutation(view, "multi-swap-play"),
    ).json()

    for index, group in enumerate(("lineup", "rotation", "bullpen"), start=1):
        team = next(
            item for item in view["teams"] if item["team_id"] == view["user_team_id"]
        )
        outgoing = team[group][0]
        candidates = client.get(
            f"/api/managers/{manager_id}/roster-candidates",
            params={
                "team_id": team["team_id"],
                "outgoing_card_id": outgoing["card_id"],
            },
        ).json()["candidates"]
        incoming = next(
            item
            for item in candidates
            if item["tier"] == "N" and item["role"] == outgoing.get("role")
        )
        response = client.post(
            f"/api/managers/{manager_id}/replace-card",
            json={
                **_mutation(view, f"multi-swap-{index}"),
                "team_id": team["team_id"],
                "outgoing_card_id": outgoing["card_id"],
                "incoming_card_id": incoming["card_id"],
            },
        )
        assert response.status_code == 200, response.text
        view = response.json()

    restarted = _client(database)
    loaded = restarted.get(f"/api/managers/{manager_id}")
    assert loaded.status_code == 200
    assert loaded.json() == view
    continued = restarted.post(
        f"/api/managers/{manager_id}/simulate-next-game",
        json=_mutation(view, "multi-swap-continue"),
    )
    assert continued.status_code == 200
    assert continued.json()["games_completed"] == 2


def test_legacy_ai_names_and_stale_pitcher_tracking_are_repaired_on_load(
    tmp_path: Path,
) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    view = _create(client, "legacy-repair-create")
    manager_id = view["manager_id"]
    team = view["teams"][0]
    outgoing = team["rotation"][0]["card_id"]
    candidates = client.get(
        f"/api/managers/{manager_id}/roster-candidates",
        params={"team_id": team["team_id"], "outgoing_card_id": outgoing},
    ).json()["candidates"]
    incoming = next(item for item in candidates if item["tier"] == "N")["card_id"]

    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT state_json FROM manager_leagues WHERE manager_id=?", (manager_id,)
        ).fetchone()[0]
        payload = json.loads(raw)
        for index, saved_team in enumerate(payload["teams"], start=1):
            saved_team["name"] = f"AI Team {index}"
        payload["teams"][0]["rotation_card_ids"][0] = incoming
        payload["rotation_plans"][0][1] = [
            incoming if card_id == outgoing else card_id
            for card_id in payload["rotation_plans"][0][1]
        ]
        connection.execute(
            "UPDATE manager_leagues SET state_json=? WHERE manager_id=?",
            (json.dumps(payload), manager_id),
        )

    repaired = _client(database).get(f"/api/managers/{manager_id}")
    assert repaired.status_code == 200
    loaded = repaired.json()
    assert [item["name"] for item in loaded["teams"]] == [
        "中信兄弟",
        "統一7-ELEVEn獅",
        "樂天桃猿",
        "味全龍",
        "富邦悍將",
        "台鋼雄鷹",
    ]
    assert loaded["teams"][0]["rotation"][0]["card_id"] == incoming


def test_over_budget_roster_is_editable_state_not_a_corrupt_save(tmp_path: Path) -> None:
    database = tmp_path / "managers.sqlite3"
    client = _client(database)
    view = _create(client, "over-budget-create")
    manager_id = view["manager_id"]
    view = client.post(
        f"/api/managers/{manager_id}/rename-team",
        json={**_mutation(view, "over-budget-unlock"), "name": "8add9"},
    ).json()
    team = view["teams"][0]
    outgoing = min(team["lineup"], key=lambda item: item["cost"])
    candidates = client.get(
        f"/api/managers/{manager_id}/roster-candidates",
        params={"team_id": team["team_id"], "outgoing_card_id": outgoing["card_id"]},
    ).json()["candidates"]
    incoming = next(item for item in candidates if item["tier"] == "SSR")
    view = client.post(
        f"/api/managers/{manager_id}/replace-card",
        json={
            **_mutation(view, "over-budget-star"),
            "team_id": team["team_id"],
            "outgoing_card_id": outgoing["card_id"],
            "incoming_card_id": incoming["card_id"],
        },
    ).json()
    view = client.post(
        f"/api/managers/{manager_id}/rename-team",
        json={**_mutation(view, "over-budget-lock"), "name": "中信兄弟"},
    ).json()
    assert view["teams"][0]["roster_cost"] > 70

    loaded = _client(database).get(f"/api/managers/{manager_id}")
    assert loaded.status_code == 200
    assert loaded.json() == view


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
    assert renamed_team["sr_limit"] is None

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

    expanded = rotated
    swap_index = 0
    while True:
        expanded_team = next(
            team for team in expanded["teams"] if team["team_id"] == expanded["user_team_id"]
        )
        if expanded_team["roster_cost"] > 70 and expanded_team["tier_counts"]["SSR"] > 2:
            break
        outgoing = next(card for card in expanded_team["lineup"] if card["tier"] != "SSR")
        candidates = client.get(
            f"/api/managers/{manager_id}/roster-candidates",
            params={
                "team_id": expanded_team["team_id"],
                "outgoing_card_id": outgoing["card_id"],
            },
        ).json()["candidates"]
        incoming = next(card for card in candidates if card["tier"] == "SSR")
        swap_index += 1
        response = client.post(
            f"/api/managers/{manager_id}/replace-card",
            json={
                **_mutation(expanded, f"unlimited-star-{swap_index}"),
                "team_id": expanded_team["team_id"],
                "outgoing_card_id": outgoing["card_id"],
                "incoming_card_id": incoming["card_id"],
            },
        )
        assert response.status_code == 200, response.text
        expanded = response.json()

    expanded_team = next(
        team for team in expanded["teams"] if team["team_id"] == expanded["user_team_id"]
    )
    reordered = [
        expanded_team["lineup"][1],
        expanded_team["lineup"][0],
        *expanded_team["lineup"][2:],
    ]
    lineup_response = client.post(
        f"/api/managers/{manager_id}/lineup",
        json={
            **_mutation(expanded, "unlimited-lineup"),
            "lineup": [
                {"card_id": card["card_id"], "position": card["position"]}
                for card in reordered
            ],
        },
    )
    assert lineup_response.status_code == 200, lineup_response.text
    expanded = lineup_response.json()
    assert expanded["teams"][0]["lineup"][0]["card_id"] == reordered[0]["card_id"]

    played = client.post(
        f"/api/managers/{manager_id}/simulate-next-game",
        json=_mutation(expanded, "unlimited-play"),
    )
    assert played.status_code == 200, played.text
    assert played.json()["games_completed"] == 1

    restarted = _client(database)
    assert restarted.get(f"/api/managers/{manager_id}").json() == played.json()
