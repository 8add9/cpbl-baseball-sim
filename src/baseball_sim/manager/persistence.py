"""Compact serialization for the authoritative Manager league state."""

from __future__ import annotations

from typing import Any, cast

from .cards import CardCatalog
from .game_roster import LineupEntry, create_team_game_roster
from .league import (
    MANAGER_LEAGUE_VERSION,
    ManagerLeagueState,
    ManagerTeamConfig,
    ManagerTeamState,
)
from .roster import RosterSelection
from .season import GameResult, generate_schedule
from .usage import PitcherAvailability

MANAGER_SAVE_SCHEMA_VERSION = 1


def manager_state_to_dict(state: ManagerLeagueState) -> dict[str, object]:
    return {
        "schema_version": MANAGER_SAVE_SCHEMA_VERSION,
        "model_version": state.version,
        "seed": state.seed,
        "catalog_snapshot_version": state.catalog.snapshot_version,
        "catalog_fingerprint": state.catalog.fingerprint,
        "teams": [
            {
                "team_id": team.config.team_id,
                "name": team.config.name,
                "strategy": team.config.strategy,
                "batter_card_ids": list(team.config.roster.batter_card_ids),
                "rotation_card_ids": list(team.config.roster.rotation_card_ids),
                "bullpen_card_ids": list(team.config.roster.bullpen_card_ids),
                "lineup": [
                    {"card_id": entry.card_id, "position": entry.position}
                    for entry in team.config.lineup
                ],
                "usage": {
                    "team_games_played": team.pitcher_availability.team_games_played,
                    "next_rotation_index": team.pitcher_availability.next_rotation_index,
                    "last_start_games": [
                        [card_id, game]
                        for card_id, game in team.pitcher_availability.last_start_games
                    ],
                    "relief_streaks": [
                        [card_id, streak]
                        for card_id, streak in team.pitcher_availability.relief_streaks
                    ],
                },
            }
            for team in state.teams
        ],
        "results": [
            {
                "game_number": result.game_number,
                "away_team_id": result.away_team_id,
                "home_team_id": result.home_team_id,
                "away_runs": result.away_runs,
                "home_runs": result.home_runs,
            }
            for result in state.results
        ],
    }


def _dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _pairs(
    value: object, label: str, *, allow_none: bool
) -> tuple[tuple[str, int | None], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    pairs: list[tuple[str, int | None]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
            raise ValueError(f"{label} entries are invalid")
        number = item[1]
        if number is None and allow_none:
            pairs.append((item[0], None))
        elif isinstance(number, int) and not isinstance(number, bool):
            pairs.append((item[0], number))
        else:
            raise ValueError(f"{label} values are invalid")
    return tuple(pairs)


def manager_state_from_dict(value: object, catalog: CardCatalog) -> ManagerLeagueState:
    root = _dict(value, "Manager save")
    if root.get("schema_version") != MANAGER_SAVE_SCHEMA_VERSION:
        raise ValueError("unsupported Manager save schema")
    if root.get("model_version") != MANAGER_LEAGUE_VERSION:
        raise ValueError("unsupported Manager league model")
    if root.get("catalog_snapshot_version") != catalog.snapshot_version or (
        root.get("catalog_fingerprint") != catalog.fingerprint
    ):
        raise ValueError("Manager save catalog fingerprint/version mismatch")
    teams_raw = root.get("teams")
    results_raw = root.get("results")
    if not isinstance(teams_raw, list) or not isinstance(results_raw, list):
        raise ValueError("Manager teams and results must be arrays")

    states: list[ManagerTeamState] = []
    claimed_cards: set[str] = set()
    for item in teams_raw:
        data = _dict(item, "Manager team")
        lineup_raw = data.get("lineup")
        if not isinstance(lineup_raw, list):
            raise ValueError("Manager lineup must be an array")
        selection = RosterSelection(
            _strings(data.get("batter_card_ids"), "batter cards"),
            _strings(data.get("rotation_card_ids"), "rotation cards"),
            _strings(data.get("bullpen_card_ids"), "bullpen cards"),
        )
        if not claimed_cards.isdisjoint(selection.all_card_ids):
            raise ValueError("Manager save reuses a CardID across teams")
        claimed_cards.update(selection.all_card_ids)
        lineup = tuple(
            LineupEntry(
                str(_dict(entry, "lineup entry")["card_id"]),
                str(_dict(entry, "lineup entry")["position"]),
            )
            for entry in lineup_raw
        )
        config = ManagerTeamConfig(
            team_id=str(data["team_id"]),
            roster=selection,
            lineup=lineup,
            name=str(data["name"]),
            strategy=str(data["strategy"]),
        )
        create_team_game_roster(
            catalog,
            selection,
            lineup,
            selection.rotation_card_ids[0],
        )
        usage_data = _dict(data.get("usage"), "pitcher usage")
        usage = PitcherAvailability(
            catalog=catalog,
            rotation_card_ids=selection.rotation_card_ids,
            bullpen_card_ids=selection.bullpen_card_ids,
            team_games_played=int(usage_data["team_games_played"]),
            next_rotation_index=int(usage_data["next_rotation_index"]),
            last_start_games=_pairs(
                usage_data.get("last_start_games"), "last starts", allow_none=True
            ),
            relief_streaks=tuple(
                (card_id, cast(int, streak))
                for card_id, streak in _pairs(
                    usage_data.get("relief_streaks"),
                    "relief streaks",
                    allow_none=False,
                )
            ),
        )
        states.append(ManagerTeamState(config, usage))

    results = tuple(
        GameResult(
            int(data["game_number"]),
            str(data["away_team_id"]),
            str(data["home_team_id"]),
            int(data["away_runs"]),
            int(data["home_runs"]),
        )
        for item in results_raw
        for data in [_dict(item, "Manager result")]
    )
    participation = {state.config.team_id: 0 for state in states}
    for result in results:
        participation[result.away_team_id] = participation.get(result.away_team_id, -1) + 1
        participation[result.home_team_id] = participation.get(result.home_team_id, -1) + 1
    if any(
        participation.get(state.config.team_id) != state.pitcher_availability.team_games_played
        for state in states
    ):
        raise ValueError("Manager save result and pitcher-usage counts disagree")
    seed = int(root["seed"])
    team_ids = tuple(state.config.team_id for state in states)
    return ManagerLeagueState(
        catalog=catalog,
        seed=seed,
        teams=tuple(states),
        schedule=generate_schedule(team_ids, seed),
        results=results,
        version=MANAGER_LEAGUE_VERSION,
    )
