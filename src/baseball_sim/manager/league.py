"""Deterministic Manager league orchestration over rosters, games, and standings."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .cards import CardCatalog
from .franchise import ManagerFranchise, advance_to_next_season, create_franchise
from .game_roster import LineupEntry, TeamGameRoster, create_team_game_roster
from .game_simulation import create_manager_game, simulate_manager_game
from .player_stats import PlayerSeasonStat, game_stat_deltas, merge_player_season_stats
from .roster import RosterRules, RosterSelection, evaluate_roster
from .season import GameResult, ScheduledGame, Standings, generate_schedule
from .usage import (
    PitcherAvailability,
    PitcherUsageEvent,
    apply_pitcher_usage,
    available_bullpen,
    create_pitcher_availability,
    select_next_starter,
)

MANAGER_LEAGUE_VERSION = "manager-league-v0.1"


@dataclass(frozen=True, slots=True)
class ManagerSeasonArchive:
    season_year: int
    results: tuple[GameResult, ...]
    player_stats: tuple[PlayerSeasonStat, ...]


@dataclass(frozen=True, slots=True)
class ManagerTeamConfig:
    team_id: str
    roster: RosterSelection
    lineup: tuple[LineupEntry, ...]
    name: str | None = None
    strategy: str = "custom"

    def __post_init__(self) -> None:
        if not self.team_id.strip():
            raise ValueError("Manager team_id cannot be blank")
        if len(self.lineup) != 9:
            raise ValueError("Manager team lineup must contain nine entries")
        if self.name is None:
            object.__setattr__(self, "name", self.team_id)
        elif not self.name.strip():
            raise ValueError("Manager team name cannot be blank")
        if not self.strategy.strip():
            raise ValueError("Manager team strategy cannot be blank")


@dataclass(frozen=True, slots=True)
class ManagerTeamState:
    config: ManagerTeamConfig
    pitcher_availability: PitcherAvailability


@dataclass(frozen=True, slots=True)
class ManagerLeagueState:
    catalog: CardCatalog
    seed: int
    teams: tuple[ManagerTeamState, ...]
    schedule: tuple[ScheduledGame, ...]
    results: tuple[GameResult, ...] = ()
    version: str = MANAGER_LEAGUE_VERSION
    season_year: int = 2026
    user_team_id: str = ""
    rotation_plans: tuple[tuple[str, tuple[str, ...]], ...] = ()
    franchise: ManagerFranchise | None = None
    player_stats: tuple[PlayerSeasonStat, ...] = ()
    settled_game_ids: tuple[str, ...] = ()
    season_history: tuple[ManagerSeasonArchive, ...] = ()

    def __post_init__(self) -> None:
        if self.version != MANAGER_LEAGUE_VERSION:
            raise ValueError("unsupported Manager league version")
        team_ids = tuple(team.config.team_id for team in self.teams)
        if len(team_ids) != 6 or len(set(team_ids)) != 6:
            raise ValueError("Manager league requires six unique teams")
        if len(self.schedule) != 360:
            raise ValueError("Manager league schedule must contain 360 games")
        if len(self.results) > len(self.schedule):
            raise ValueError("Manager league has more results than scheduled games")
        for index, result in enumerate(self.results):
            scheduled = self.schedule[index]
            if (
                result.game_number != scheduled.game_number
                or result.away_team_id != scheduled.away_team_id
                or result.home_team_id != scheduled.home_team_id
            ):
                raise ValueError("Manager results must follow the frozen schedule")
        if not self.user_team_id:
            object.__setattr__(self, "user_team_id", team_ids[0])
        elif self.user_team_id not in team_ids:
            raise ValueError("Manager user team must belong to the league")
        if not 1990 <= self.season_year <= 9999:
            raise ValueError("Manager season year is invalid")
        if not self.rotation_plans:
            object.__setattr__(
                self,
                "rotation_plans",
                tuple(
                    (team.config.team_id, team.config.roster.rotation_card_ids)
                    for team in self.teams
                ),
            )
        plans = dict(self.rotation_plans)
        if set(plans) != set(team_ids) or len(plans) != len(self.rotation_plans):
            raise ValueError("rotation plans must cover each Manager team once")
        for team in self.teams:
            plan = plans[team.config.team_id]
            if len(plan) != 4 or not set(plan).issubset(team.config.roster.rotation_card_ids):
                raise ValueError("rotation plan must contain four owned SP slots")
        if self.franchise is None:
            object.__setattr__(
                self,
                "franchise",
                create_franchise(team_ids, self.season_year),
            )
        elif (
            self.franchise.active_season_year != self.season_year
            or set(self.franchise.team_ids) != set(team_ids)
        ):
            raise ValueError("Manager franchise does not match active league season")
        if len(set(self.settled_game_ids)) != len(self.settled_game_ids):
            raise ValueError("settled Manager game IDs must be unique")
        expected_ids = tuple(
            f"{self.season_year}:{result.game_number}" for result in self.results
        )
        if not self.settled_game_ids and self.results:
            object.__setattr__(self, "settled_game_ids", expected_ids)
        elif self.settled_game_ids != expected_ids:
            raise ValueError("settled Manager games must match active results")
        if any(item.season_year != self.season_year for item in self.player_stats):
            raise ValueError("active player stats must match Manager season")

    @property
    def finished(self) -> bool:
        return len(self.results) == len(self.schedule)

    @property
    def next_game(self) -> ScheduledGame | None:
        return None if self.finished else self.schedule[len(self.results)]

    @property
    def standings(self) -> Standings:
        return Standings.from_results(
            tuple(team.config.team_id for team in self.teams), self.results
        )


def create_manager_league(
    catalog: CardCatalog,
    teams: tuple[ManagerTeamConfig, ...],
    *,
    seed: int,
) -> ManagerLeagueState:
    if len(teams) != 6 or len({team.team_id for team in teams}) != 6:
        raise ValueError("Manager league requires six unique team configs")
    claimed_cards: set[str] = set()
    states: list[ManagerTeamState] = []
    for team in teams:
        legality = evaluate_roster(catalog, team.roster)
        if not legality.legal:
            raise ValueError(f"illegal roster for {team.team_id}: {legality.violations}")
        overlap = claimed_cards.intersection(team.roster.all_card_ids)
        if overlap:
            raise ValueError("the same CardID cannot be owned by two league teams")
        create_team_game_roster(
            catalog,
            team.roster,
            team.lineup,
            team.roster.rotation_card_ids[0],
        )
        claimed_cards.update(team.roster.all_card_ids)
        usage = create_pitcher_availability(
            catalog, team.roster.rotation_card_ids, team.roster.bullpen_card_ids
        )
        states.append(ManagerTeamState(team, usage))
    schedule = generate_schedule(tuple(team.team_id for team in teams), seed)
    return ManagerLeagueState(catalog, seed, tuple(states), schedule)


def _game_seed(seed: int, season_year: int, scheduled: ScheduledGame) -> int:
    payload = (
        f"{MANAGER_LEAGUE_VERSION}:{seed}:{season_year}:{scheduled.game_number}:"
        f"{scheduled.away_team_id}:{scheduled.home_team_id}"
    ).encode()
    digest = hashlib.blake2b(payload, digest_size=8, person=b"mgrleague").digest()
    return int.from_bytes(digest, "big")


def _game_roster(
    state: ManagerTeamState, preferred_starter: str
) -> tuple[TeamGameRoster, str]:
    starter = select_next_starter(state.pitcher_availability, preferred_starter)
    available = set(available_bullpen(state.pitcher_availability))
    unavailable = tuple(
        card_id
        for card_id in state.config.roster.bullpen_card_ids
        if card_id not in available
    )
    roster = create_team_game_roster(
        state.pitcher_availability.catalog,
        state.config.roster,
        state.config.lineup,
        starter,
        unavailable,
        RosterRules(
            roster_size=len(state.config.roster.all_card_ids),
            batter_count=len(state.config.roster.batter_card_ids),
            rotation_count=len(state.config.roster.rotation_card_ids),
            bullpen_count=len(state.config.roster.bullpen_card_ids),
            budget=None,
            max_ssr=None,
            max_sr=len(state.config.roster.all_card_ids),
        ),
    )
    return roster, starter


def simulate_next_league_game(state: ManagerLeagueState) -> ManagerLeagueState:
    scheduled = state.next_game
    if scheduled is None:
        raise ValueError("Manager league season is complete")
    by_id = {team.config.team_id: team for team in state.teams}
    away_state = by_id[scheduled.away_team_id]
    home_state = by_id[scheduled.home_team_id]
    plans = dict(state.rotation_plans)
    away_plan = plans[scheduled.away_team_id]
    home_plan = plans[scheduled.home_team_id]
    away_roster, away_starter = _game_roster(
        away_state,
        away_plan[away_state.pitcher_availability.team_games_played % 4],
    )
    home_roster, home_starter = _game_roster(
        home_state,
        home_plan[home_state.pitcher_availability.team_games_played % 4],
    )
    game = simulate_manager_game(
        create_manager_game(
            away_roster,
            home_roster,
            seed=_game_seed(state.seed, state.season_year, scheduled),
        )
    )
    result = GameResult(
        scheduled.game_number,
        scheduled.away_team_id,
        scheduled.home_team_id,
        game.final_state.away_score,
        game.final_state.home_score,
    )
    away_usage = apply_pitcher_usage(
        away_state.pitcher_availability,
        PitcherUsageEvent(
            away_state.pitcher_availability.next_game_number,
            away_starter,
            game.away_roster.used_pitcher_card_ids,
        ),
    )
    home_usage = apply_pitcher_usage(
        home_state.pitcher_availability,
        PitcherUsageEvent(
            home_state.pitcher_availability.next_game_number,
            home_starter,
            game.home_roster.used_pitcher_card_ids,
        ),
    )
    updated = tuple(
        ManagerTeamState(
            team.config,
            away_usage
            if team.config.team_id == scheduled.away_team_id
            else home_usage
            if team.config.team_id == scheduled.home_team_id
            else team.pitcher_availability,
        )
        for team in state.teams
    )
    settled_id = f"{state.season_year}:{scheduled.game_number}"
    if settled_id in state.settled_game_ids:
        raise ValueError("Manager game was already settled")
    player_stats = state.player_stats
    for delta in game_stat_deltas(game, state.season_year):
        player_stats = merge_player_season_stats(player_stats, delta)
    return replace(
        state,
        teams=updated,
        results=state.results + (result,),
        player_stats=player_stats,
        settled_game_ids=state.settled_game_ids + (settled_id,),
    )


def simulate_league_games(
    state: ManagerLeagueState, games: int
) -> ManagerLeagueState:
    if games <= 0:
        raise ValueError("games must be positive")
    if len(state.results) + games > len(state.schedule):
        raise ValueError("requested games exceed the Manager league schedule")
    result = state
    for _ in range(games):
        result = simulate_next_league_game(result)
    return result


def simulate_manager_season(state: ManagerLeagueState) -> ManagerLeagueState:
    if state.finished:
        return state
    return simulate_league_games(state, len(state.schedule) - len(state.results))


def start_next_manager_season(state: ManagerLeagueState) -> ManagerLeagueState:
    if not state.finished:
        raise ValueError("Manager season must be complete before advancing")
    assert state.franchise is not None
    order = tuple(row.team_id for row in state.standings.rows)
    franchise = advance_to_next_season(state.franchise, order)
    archive = ManagerSeasonArchive(state.season_year, state.results, state.player_stats)
    teams = tuple(
        ManagerTeamState(
            team.config,
            create_pitcher_availability(
                state.catalog,
                team.config.roster.rotation_card_ids,
                team.config.roster.bullpen_card_ids,
            ),
        )
        for team in state.teams
    )
    return ManagerLeagueState(
        catalog=state.catalog,
        seed=state.seed,
        teams=teams,
        schedule=generate_schedule(tuple(team.config.team_id for team in teams), state.seed),
        season_year=state.season_year + 1,
        user_team_id=state.user_team_id,
        rotation_plans=state.rotation_plans,
        franchise=franchise,
        season_history=state.season_history + (archive,),
    )
