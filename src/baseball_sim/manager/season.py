"""Pure deterministic league schedules and standings for Manager Mode."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

TEAM_COUNT = 6
OPPONENT_GAMES = 24
HOME_GAMES_PER_OPPONENT = OPPONENT_GAMES // 2
ROUNDS_PER_ROUND_ROBIN = TEAM_COUNT - 1
GAMES_PER_ROUND = TEAM_COUNT // 2
ROUNDS_PER_SEASON = ROUNDS_PER_ROUND_ROBIN * OPPONENT_GAMES
LEAGUE_GAMES = ROUNDS_PER_SEASON * GAMES_PER_ROUND
TEAM_GAMES = OPPONENT_GAMES * (TEAM_COUNT - 1)


@dataclass(frozen=True, slots=True)
class ScheduledGame:
    """One game in the frozen 120-round, six-team schedule."""

    game_number: int
    round_number: int
    away_team_id: str
    home_team_id: str

    def __post_init__(self) -> None:
        if self.game_number <= 0 or self.round_number <= 0:
            raise ValueError("schedule numbers must be positive")
        if not self.away_team_id or not self.home_team_id:
            raise ValueError("scheduled team ids cannot be empty")
        if self.away_team_id == self.home_team_id:
            raise ValueError("a team cannot play itself")


@dataclass(frozen=True, slots=True)
class GameResult:
    """Final, tie-free result for one scheduled Manager Mode game."""

    game_number: int
    away_team_id: str
    home_team_id: str
    away_runs: int
    home_runs: int

    def __post_init__(self) -> None:
        if self.game_number <= 0:
            raise ValueError("game_number must be positive")
        if not self.away_team_id or not self.home_team_id:
            raise ValueError("result team ids cannot be empty")
        if self.away_team_id == self.home_team_id:
            raise ValueError("a team cannot play itself")
        if self.away_runs < 0 or self.home_runs < 0:
            raise ValueError("runs cannot be negative")
        if self.away_runs == self.home_runs:
            raise ValueError("Manager Mode games cannot end in a tie")


@dataclass(frozen=True, slots=True)
class Standing:
    team_id: str
    wins: int
    losses: int
    runs_scored: int
    runs_allowed: int
    winning_percentage: float
    games_behind: float

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def run_differential(self) -> int:
        return self.runs_scored - self.runs_allowed


@dataclass(frozen=True, slots=True)
class Standings:
    """Ranked immutable standings using the frozen v0.1 tie-break contract."""

    rows: tuple[Standing, ...]
    results_count: int

    @classmethod
    def from_results(
        cls, team_ids: Sequence[str], results: Iterable[GameResult]
    ) -> Standings:
        teams = _validated_team_ids(team_ids)
        known = set(teams)
        materialized = tuple(results)
        game_numbers = [result.game_number for result in materialized]
        if len(game_numbers) != len(set(game_numbers)):
            raise ValueError("game results contain duplicate game numbers")

        wins: Counter[str] = Counter()
        losses: Counter[str] = Counter()
        scored: Counter[str] = Counter()
        allowed: Counter[str] = Counter()
        for result in materialized:
            if result.away_team_id not in known or result.home_team_id not in known:
                raise ValueError("game result contains a team outside the league")
            scored[result.away_team_id] += result.away_runs
            scored[result.home_team_id] += result.home_runs
            allowed[result.away_team_id] += result.home_runs
            allowed[result.home_team_id] += result.away_runs
            if result.away_runs > result.home_runs:
                winner, loser = result.away_team_id, result.home_team_id
            else:
                winner, loser = result.home_team_id, result.away_team_id
            wins[winner] += 1
            losses[loser] += 1

        summaries = [
            (
                team,
                wins[team],
                losses[team],
                scored[team],
                allowed[team],
            )
            for team in teams
        ]

        def ranking_key(summary: tuple[str, int, int, int, int]) -> tuple[object, ...]:
            team, team_wins, team_losses, runs_scored, runs_allowed = summary
            games = team_wins + team_losses
            percentage = Fraction(team_wins, games) if games else Fraction(0)
            return (-percentage, -(runs_scored - runs_allowed), -runs_scored, team)

        summaries.sort(key=ranking_key)
        leader_wins = summaries[0][1]
        leader_losses = summaries[0][2]
        rows = tuple(
            Standing(
                team_id=team,
                wins=team_wins,
                losses=team_losses,
                runs_scored=runs_scored,
                runs_allowed=runs_allowed,
                winning_percentage=(
                    team_wins / (team_wins + team_losses)
                    if team_wins + team_losses
                    else 0.0
                ),
                games_behind=(
                    (leader_wins - team_wins + team_losses - leader_losses) / 2.0
                ),
            )
            for team, team_wins, team_losses, runs_scored, runs_allowed in summaries
        )
        return cls(rows=rows, results_count=len(materialized))


def _validated_team_ids(team_ids: Sequence[str]) -> tuple[str, ...]:
    teams = tuple(team_ids)
    if len(teams) != TEAM_COUNT:
        raise ValueError(f"Manager Mode requires exactly {TEAM_COUNT} teams")
    if any(not isinstance(team, str) or not team.strip() for team in teams):
        raise ValueError("team ids must be non-empty strings")
    if len(set(teams)) != len(teams):
        raise ValueError("team ids must be unique")
    return tuple(sorted(teams))


def _seeded_team_order(team_ids: tuple[str, ...], seed: int) -> list[str]:
    """Order teams with a version-independent digest instead of mutable RNG state."""

    def key(team_id: str) -> tuple[bytes, str]:
        payload = f"manager-schedule-v0.1:{seed}:{team_id}".encode()
        return hashlib.blake2b(payload, digest_size=16, person=b"mgrsched").digest(), team_id

    return sorted(team_ids, key=key)


def _round_robin_pairs(team_order: list[str]) -> tuple[tuple[tuple[str, str], ...], ...]:
    rotating = list(team_order)
    rounds: list[tuple[tuple[str, str], ...]] = []
    for round_index in range(ROUNDS_PER_ROUND_ROBIN):
        pairs: list[tuple[str, str]] = []
        for pair_index in range(GAMES_PER_ROUND):
            first = rotating[pair_index]
            second = rotating[-(pair_index + 1)]
            if (round_index + pair_index) % 2:
                first, second = second, first
            pairs.append((first, second))
        rounds.append(tuple(pairs))
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    return tuple(rounds)


def generate_schedule(team_ids: Sequence[str], seed: int) -> tuple[ScheduledGame, ...]:
    """Create 360 games: every pair plays 24 times, split 12 home and 12 away."""

    teams = _validated_team_ids(team_ids)
    base_rounds = _round_robin_pairs(_seeded_team_order(teams, seed))
    games: list[ScheduledGame] = []
    for meeting_index in range(OPPONENT_GAMES):
        reverse_home = meeting_index % 2 == 1
        for round_index, pairs in enumerate(base_rounds):
            round_number = meeting_index * ROUNDS_PER_ROUND_ROBIN + round_index + 1
            for first, second in pairs:
                away, home = (second, first) if reverse_home else (first, second)
                games.append(
                    ScheduledGame(
                        game_number=len(games) + 1,
                        round_number=round_number,
                        away_team_id=away,
                        home_team_id=home,
                    )
                )
    return tuple(games)
