"""Compact serialization for the authoritative Manager league state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast

from .cards import CardCatalog
from .customization import AI_CPBL_TEAM_NAMES
from .franchise import (
    ManagerFranchise,
    RewardGrant,
    SeasonPlacement,
    TeamEntitlement,
)
from .game_roster import LineupEntry, create_team_game_roster
from .league import (
    MANAGER_LEAGUE_VERSION,
    ManagerLeagueState,
    ManagerSeasonArchive,
    ManagerTeamConfig,
    ManagerTeamState,
)
from .player_stats import BatterStatLine, PitcherStatLine, PlayerSeasonStat
from .roster import RosterRules, RosterSelection
from .season import GameResult, generate_schedule
from .usage import PitcherAvailability

MANAGER_SAVE_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class _LoadedV2:
    season_year: int
    user_team_id: str
    rotation_plans: tuple[tuple[str, tuple[str, ...]], ...]
    franchise: ManagerFranchise
    player_stats: tuple[PlayerSeasonStat, ...]
    settled_game_ids: tuple[str, ...]
    season_history: tuple[ManagerSeasonArchive, ...]


def manager_state_to_dict(state: ManagerLeagueState) -> dict[str, object]:
    return {
        "schema_version": MANAGER_SAVE_SCHEMA_VERSION,
        "model_version": state.version,
        "seed": state.seed,
        "catalog_snapshot_version": state.catalog.snapshot_version,
        "catalog_fingerprint": state.catalog.fingerprint,
        "season_year": state.season_year,
        "user_team_id": state.user_team_id,
        "rotation_plans": [
            [team_id, list(plan)] for team_id, plan in state.rotation_plans
        ],
        "franchise": {
            "version": state.franchise.version,
            "active_season_year": state.franchise.active_season_year,
            "team_ids": list(state.franchise.team_ids),
            "history": [asdict(item) for item in state.franchise.history],
            "reward_grants": [asdict(item) for item in state.franchise.reward_grants],
            "entitlements": [asdict(item) for item in state.franchise.entitlements],
        }
        if state.franchise is not None
        else None,
        "player_stats": [_player_stat_to_dict(item) for item in state.player_stats],
        "settled_game_ids": list(state.settled_game_ids),
        "season_history": [
            {
                "season_year": archive.season_year,
                "results": [_result_to_dict(item) for item in archive.results],
                "player_stats": [
                    _player_stat_to_dict(item) for item in archive.player_stats
                ],
            }
            for archive in state.season_history
        ],
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
        "results": [_result_to_dict(result) for result in state.results],
    }


def _result_to_dict(result: GameResult) -> dict[str, object]:
    return {
        "game_number": result.game_number,
        "away_team_id": result.away_team_id,
        "home_team_id": result.home_team_id,
        "away_runs": result.away_runs,
        "home_runs": result.home_runs,
    }


def _player_stat_to_dict(item: PlayerSeasonStat) -> dict[str, object]:
    return {
        "card_id": item.card_id,
        "team_id": item.team_id,
        "season_year": item.season_year,
        "batter": None if item.batter is None else asdict(item.batter),
        "pitcher": None if item.pitcher is None else asdict(item.pitcher),
        "version": item.version,
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


def _aligned_tracking(
    pairs: tuple[tuple[str, int | None], ...], current_card_ids: tuple[str, ...]
) -> tuple[tuple[str, int | None], ...]:
    """Repair saves written before roster swaps updated pitcher tracking keys."""
    if len(pairs) != len(current_card_ids):
        return pairs
    values = dict(pairs)
    if set(values) == set(current_card_ids):
        return tuple((card_id, values[card_id]) for card_id in current_card_ids)
    return tuple(
        (card_id, pairs[index][1]) for index, card_id in enumerate(current_card_ids)
    )


def _team_name(team_id: str, saved_name: object) -> str:
    name = str(saved_name).strip()
    for index, real_name in enumerate(AI_CPBL_TEAM_NAMES, start=1):
        if team_id == f"team-{index}" and name.casefold() in {
            f"ai team {index}",
            f"ai team{index}",
        }:
            return real_name
    return name


def manager_state_from_dict(value: object, catalog: CardCatalog) -> ManagerLeagueState:
    root = _dict(value, "Manager save")
    schema_version = root.get("schema_version")
    if schema_version not in {1, MANAGER_SAVE_SCHEMA_VERSION}:
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
            name=_team_name(str(data["team_id"]), data["name"]),
            strategy=str(data["strategy"]),
        )
        structural_rules = RosterRules(
            roster_size=len(selection.all_card_ids),
            batter_count=len(selection.batter_card_ids),
            rotation_count=len(selection.rotation_card_ids),
            bullpen_count=len(selection.bullpen_card_ids),
            budget=None,
            max_ssr=None,
            max_sr=len(selection.all_card_ids),
        )
        create_team_game_roster(
            catalog,
            selection,
            lineup,
            selection.rotation_card_ids[0],
            rules=structural_rules,
        )
        usage_data = _dict(data.get("usage"), "pitcher usage")
        last_starts = _aligned_tracking(
            _pairs(usage_data.get("last_start_games"), "last starts", allow_none=True),
            selection.rotation_card_ids,
        )
        relief_streaks = _aligned_tracking(
            _pairs(usage_data.get("relief_streaks"), "relief streaks", allow_none=False),
            selection.bullpen_card_ids,
        )
        usage = PitcherAvailability(
            catalog=catalog,
            rotation_card_ids=selection.rotation_card_ids,
            bullpen_card_ids=selection.bullpen_card_ids,
            team_games_played=int(usage_data["team_games_played"]),
            next_rotation_index=int(usage_data["next_rotation_index"]),
            last_start_games=last_starts,
            relief_streaks=tuple(
                (card_id, cast(int, streak))
                for card_id, streak in relief_streaks
            ),
        )
        states.append(ManagerTeamState(config, usage))

    results = tuple(_load_result(item) for item in results_raw)
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
    if schema_version == 1:
        return ManagerLeagueState(
            catalog=catalog,
            seed=seed,
            teams=tuple(states),
            schedule=generate_schedule(team_ids, seed),
            results=results,
            version=MANAGER_LEAGUE_VERSION,
        )
    owner_by_card = {
        card_id: state.config.team_id
        for state in states
        for card_id in state.config.roster.all_card_ids
    }
    extra = _load_v2_fields(root, owner_by_card)
    return ManagerLeagueState(
        catalog=catalog,
        seed=seed,
        teams=tuple(states),
        schedule=generate_schedule(team_ids, seed),
        results=results,
        version=MANAGER_LEAGUE_VERSION,
        season_year=extra.season_year,
        user_team_id=extra.user_team_id,
        rotation_plans=extra.rotation_plans,
        franchise=extra.franchise,
        player_stats=extra.player_stats,
        settled_game_ids=extra.settled_game_ids,
        season_history=extra.season_history,
    )


def _load_result(value: object) -> GameResult:
    data = _dict(value, "Manager result")
    return GameResult(
        int(data["game_number"]),
        str(data["away_team_id"]),
        str(data["home_team_id"]),
        int(data["away_runs"]),
        int(data["home_runs"]),
    )


def _load_player_stat(
    value: object, owner_by_card: dict[str, str] | None = None
) -> PlayerSeasonStat:
    data = _dict(value, "player stat")
    batter_raw = data.get("batter")
    pitcher_raw = data.get("pitcher")
    return PlayerSeasonStat(
        card_id=str(data["card_id"]),
        season_year=int(data["season_year"]),
        batter=None
        if batter_raw is None
        else BatterStatLine(**_dict(batter_raw, "batter stat")),
        pitcher=None
        if pitcher_raw is None
        else PitcherStatLine(**_dict(pitcher_raw, "pitcher stat")),
        team_id=str(
            data.get("team_id")
            or (owner_by_card or {}).get(str(data["card_id"]), "")
        ),
        version=str(data["version"]),
    )


def _load_v2_fields(
    root: dict[str, Any], owner_by_card: dict[str, str]
) -> _LoadedV2:
    franchise_raw = _dict(root["franchise"], "Manager franchise")
    franchise = ManagerFranchise(
        active_season_year=int(franchise_raw["active_season_year"]),
        team_ids=_strings(franchise_raw["team_ids"], "franchise teams"),
        history=tuple(
            SeasonPlacement(
                int(item["season_year"]),
                tuple(item["ordered_team_ids"]),
            )
            for raw in franchise_raw["history"]
            for item in [_dict(raw, "season placement")]
        ),
        reward_grants=tuple(
            RewardGrant(**_dict(raw, "reward grant"))
            for raw in franchise_raw["reward_grants"]
        ),
        entitlements=tuple(
            TeamEntitlement(**_dict(raw, "team entitlement"))
            for raw in franchise_raw["entitlements"]
        ),
        version=str(franchise_raw["version"]),
    )
    history: list[ManagerSeasonArchive] = []
    for raw in root["season_history"]:
        item = _dict(raw, "season archive")
        history.append(
            ManagerSeasonArchive(
                int(item["season_year"]),
                tuple(_load_result(result) for result in item["results"]),
                tuple(
                    _load_player_stat(stat, owner_by_card)
                    for stat in item["player_stats"]
                ),
            )
        )
    return _LoadedV2(
        season_year=int(root["season_year"]),
        user_team_id=str(root["user_team_id"]),
        rotation_plans=tuple(
            (str(item[0]), tuple(str(card_id) for card_id in item[1]))
            for item in root["rotation_plans"]
        ),
        franchise=franchise,
        player_stats=tuple(
            _load_player_stat(item, owner_by_card) for item in root["player_stats"]
        ),
        settled_game_ids=_strings(root["settled_game_ids"], "settled games"),
        season_history=tuple(history),
    )
