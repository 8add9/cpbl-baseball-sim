"""Immutable Manager player-season statistical ledgers."""

from __future__ import annotations

from dataclasses import dataclass, replace

from baseball_sim.game.state import Team
from baseball_sim.simulation.outcomes import Outcome

from .game_simulation import ManagerGameResult

PLAYER_SEASON_STATS_VERSION = "manager-player-season-stats-v0.1"


@dataclass(frozen=True, slots=True)
class BatterStatLine:
    games: int = 0
    pa: int = 0
    ab: int = 0
    hits: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    walks: int = 0
    hbp: int = 0
    strikeouts: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if any(value < 0 for value in values):
            raise ValueError("batter statistics cannot be negative")
        if self.hits > self.ab or self.doubles + self.triples + self.home_runs > self.hits:
            raise ValueError("batter hit totals are inconsistent")
        if self.strikeouts > self.ab or self.ab + self.walks + self.hbp > self.pa:
            raise ValueError("batter PA totals are inconsistent")

    @property
    def total_bases(self) -> int:
        singles = self.hits - self.doubles - self.triples - self.home_runs
        return singles + 2 * self.doubles + 3 * self.triples + 4 * self.home_runs

    @property
    def avg(self) -> float:
        return self.hits / self.ab if self.ab else 0.0

    @property
    def obp(self) -> float:
        return (self.hits + self.walks + self.hbp) / self.pa if self.pa else 0.0

    @property
    def slg(self) -> float:
        return self.total_bases / self.ab if self.ab else 0.0

    @property
    def ops(self) -> float:
        return self.obp + self.slg

    def __add__(self, other: BatterStatLine) -> BatterStatLine:
        return BatterStatLine(
            **{
                name: getattr(self, name) + getattr(other, name)
                for name in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class PitcherStatLine:
    games: int = 0
    games_started: int = 0
    outs_recorded: int = 0
    batters_faced: int = 0
    hits: int = 0
    home_runs: int = 0
    walks: int = 0
    hbp: int = 0
    strikeouts: int = 0
    runs: int = 0
    wins: int = 0
    losses: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if any(value < 0 for value in values):
            raise ValueError("pitcher statistics cannot be negative")
        if self.games_started > self.games or self.strikeouts > self.outs_recorded:
            raise ValueError("pitcher game or strikeout totals are inconsistent")
        if self.wins + self.losses > self.games:
            raise ValueError("pitcher decisions cannot exceed games pitched")

    @property
    def innings_pitched(self) -> str:
        return f"{self.outs_recorded // 3}.{self.outs_recorded % 3}"

    @property
    def runs_allowed_per_nine(self) -> float:
        return self.runs * 27 / self.outs_recorded if self.outs_recorded else 0.0

    @property
    def whip(self) -> float:
        return (self.walks + self.hits) * 3 / self.outs_recorded if self.outs_recorded else 0.0

    def __add__(self, other: PitcherStatLine) -> PitcherStatLine:
        return PitcherStatLine(
            **{
                name: getattr(self, name) + getattr(other, name)
                for name in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class PlayerSeasonStat:
    card_id: str
    season_year: int
    batter: BatterStatLine | None = None
    pitcher: PitcherStatLine | None = None
    team_id: str = ""
    version: str = PLAYER_SEASON_STATS_VERSION

    def __post_init__(self) -> None:
        if not self.card_id.strip() or not 1990 <= self.season_year <= 9999:
            raise ValueError("player-season identity is invalid")
        if (self.batter is None) == (self.pitcher is None):
            raise ValueError("player season must contain exactly one stat kind")
        if self.version != PLAYER_SEASON_STATS_VERSION:
            raise ValueError("unsupported player-season stats version")


def merge_player_season_stats(
    current: tuple[PlayerSeasonStat, ...], update: PlayerSeasonStat
) -> tuple[PlayerSeasonStat, ...]:
    """Add a game line and keep the ledger in deterministic CardID order."""
    by_id = {(item.team_id, item.card_id): item for item in current}
    if len(by_id) != len(current):
        raise ValueError("player-season ledger contains duplicate team/CardIDs")
    key = (update.team_id, update.card_id)
    existing = by_id.get(key)
    if existing is None:
        by_id[key] = update
    else:
        if existing.season_year != update.season_year:
            raise ValueError("cannot merge player statistics across seasons")
        if existing.batter is not None and update.batter is not None:
            by_id[key] = PlayerSeasonStat(
                update.card_id,
                update.season_year,
                batter=existing.batter + update.batter,
                team_id=update.team_id,
            )
        elif existing.pitcher is not None and update.pitcher is not None:
            by_id[key] = PlayerSeasonStat(
                update.card_id,
                update.season_year,
                pitcher=existing.pitcher + update.pitcher,
                team_id=update.team_id,
            )
        else:
            raise ValueError("cannot change a player-season stat kind")
    return tuple(by_id[key] for key in sorted(by_id))


def game_stat_deltas(
    result: ManagerGameResult,
    season_year: int,
    away_team_id: str,
    home_team_id: str,
) -> tuple[PlayerSeasonStat, ...]:
    """Project only statistics supported by the authoritative PA transition stream."""
    batter_lines: dict[str, BatterStatLine] = {}
    pitcher_lines: dict[str, PitcherStatLine] = {}
    starters = {
        result.away_roster.used_pitcher_card_ids[0],
        result.home_roster.used_pitcher_card_ids[0],
    }
    card_teams = {
        **{
            card_id: away_team_id
            for card_id in (
                tuple(entry.card_id for entry in result.away_roster.lineup)
                + result.away_roster.bench_card_ids
                + result.away_roster.rotation_card_ids
                + result.away_roster.bullpen_card_ids
            )
        },
        **{
            card_id: home_team_id
            for card_id in (
                tuple(entry.card_id for entry in result.home_roster.lineup)
                + result.home_roster.bench_card_ids
                + result.home_roster.rotation_card_ids
                + result.home_roster.bullpen_card_ids
            )
        },
    }
    winning_pitcher, losing_pitcher = _pitcher_decisions(
        result, card_teams, away_team_id, home_team_id
    )
    for transition in result.transitions:
        outcome = transition.outcome
        hit = outcome in {Outcome.SINGLE, Outcome.DOUBLE, Outcome.TRIPLE, Outcome.HR}
        batter_delta = BatterStatLine(
            games=0,
            pa=1,
            ab=0 if outcome in {Outcome.BB, Outcome.HBP} else 1,
            hits=int(hit),
            doubles=int(outcome is Outcome.DOUBLE),
            triples=int(outcome is Outcome.TRIPLE),
            home_runs=int(outcome is Outcome.HR),
            walks=int(outcome is Outcome.BB),
            hbp=int(outcome is Outcome.HBP),
            strikeouts=int(outcome is Outcome.SO),
        )
        batter_lines[transition.batter] = (
            batter_lines.get(transition.batter, BatterStatLine()) + batter_delta
        )
        pitcher_delta = PitcherStatLine(
            batters_faced=1,
            outs_recorded=int(outcome in {Outcome.SO, Outcome.OUT}),
            hits=int(hit),
            home_runs=int(outcome is Outcome.HR),
            walks=int(outcome is Outcome.BB),
            hbp=int(outcome is Outcome.HBP),
            strikeouts=int(outcome is Outcome.SO),
            runs=transition.runs_scored,
        )
        pitcher_lines[transition.pitcher] = (
            pitcher_lines.get(transition.pitcher, PitcherStatLine()) + pitcher_delta
        )
    deltas: list[PlayerSeasonStat] = []
    for card_id, batter_line in batter_lines.items():
        deltas.append(
            PlayerSeasonStat(
                card_id,
                season_year,
                batter=replace(batter_line, games=1),
                team_id=card_teams[card_id],
            )
        )
    for card_id, pitcher_line in pitcher_lines.items():
        deltas.append(
            PlayerSeasonStat(
                card_id,
                season_year,
                pitcher=replace(
                    pitcher_line,
                    games=1,
                    games_started=int(card_id in starters),
                    wins=int(card_id == winning_pitcher),
                    losses=int(card_id == losing_pitcher),
                ),
                team_id=card_teams[card_id],
            )
        )
    return tuple(sorted(deltas, key=lambda item: (item.team_id, item.card_id)))


def _pitcher_decisions(
    result: ManagerGameResult,
    card_teams: dict[str, str],
    away_team_id: str,
    home_team_id: str,
) -> tuple[str, str]:
    """Assign one simplified pitcher win/loss from the permanent go-ahead play."""
    winner = result.final_state.winner
    if winner is None:
        raise ValueError("finished Manager game requires a winner")
    winner_team_id = away_team_id if winner is Team.AWAY else home_team_id
    loser_team_id = home_team_id if winner is Team.AWAY else away_team_id

    decisive_index = -1
    for index, transition in enumerate(result.transitions):
        state = transition.state
        winner_score = state.away_score if winner is Team.AWAY else state.home_score
        loser_score = state.home_score if winner is Team.AWAY else state.away_score
        if transition.runs_scored <= 0 or winner_score <= loser_score:
            continue
        if all(
            (
                later.state.away_score > later.state.home_score
                if winner is Team.AWAY
                else later.state.home_score > later.state.away_score
            )
            for later in result.transitions[index:]
        ):
            decisive_index = index
            break
    if decisive_index < 0:
        raise ValueError("Manager game has no permanent go-ahead play")

    losing_pitcher = result.transitions[decisive_index].pitcher
    if card_teams.get(losing_pitcher) != loser_team_id:
        raise ValueError("losing pitcher does not belong to the losing team")
    winning_pitcher = next(
        (
            transition.pitcher
            for transition in reversed(result.transitions[:decisive_index])
            if card_teams.get(transition.pitcher) == winner_team_id
        ),
        result.away_roster.used_pitcher_card_ids[0]
        if winner is Team.AWAY
        else result.home_roster.used_pitcher_card_ids[0],
    )
    return winning_pitcher, losing_pitcher
