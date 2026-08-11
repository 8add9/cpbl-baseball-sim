from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict

import pytest

from baseball_sim.manager.season import (
    GAMES_PER_ROUND,
    HOME_GAMES_PER_OPPONENT,
    LEAGUE_GAMES,
    ROUNDS_PER_SEASON,
    TEAM_GAMES,
    GameResult,
    Standings,
    generate_schedule,
)

TEAMS = ("A", "B", "C", "D", "E", "F")


def _schedule_bytes(seed: int) -> bytes:
    payload = [asdict(game) for game in generate_schedule(TEAMS, seed)]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def test_circle_schedule_has_complete_six_team_invariants() -> None:
    schedule = generate_schedule(TEAMS, seed=20260812)
    assert len(schedule) == LEAGUE_GAMES == 360
    assert [game.game_number for game in schedule] == list(range(1, 361))
    assert {game.round_number for game in schedule} == set(range(1, ROUNDS_PER_SEASON + 1))

    team_games: Counter[str] = Counter()
    pair_games: Counter[tuple[str, str]] = Counter()
    pair_home: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    by_round: dict[int, list[object]] = defaultdict(list)
    for game in schedule:
        team_games.update((game.away_team_id, game.home_team_id))
        pair = tuple(sorted((game.away_team_id, game.home_team_id)))
        pair_games[pair] += 1
        pair_home[pair][game.home_team_id] += 1
        by_round[game.round_number].append(game)

    assert team_games == Counter({team: TEAM_GAMES for team in TEAMS})
    assert len(pair_games) == 15
    assert set(pair_games.values()) == {24}
    assert all(
        home_counts == Counter({pair[0]: HOME_GAMES_PER_OPPONENT, pair[1]: HOME_GAMES_PER_OPPONENT})
        for pair, home_counts in pair_home.items()
    )
    assert len(by_round) == ROUNDS_PER_SEASON == 120
    for games in by_round.values():
        assert len(games) == GAMES_PER_ROUND == 3
        participants = [
            team
            for game in games
            for team in (game.away_team_id, game.home_team_id)
        ]
        assert sorted(participants) == sorted(TEAMS)


def test_schedule_is_byte_deterministic_and_seed_changes_only_order() -> None:
    assert _schedule_bytes(42) == _schedule_bytes(42)
    assert _schedule_bytes(42) != _schedule_bytes(43)
    assert len(generate_schedule(tuple(reversed(TEAMS)), 42)) == LEAGUE_GAMES
    assert generate_schedule(tuple(reversed(TEAMS)), 42) == generate_schedule(TEAMS, 42)


@pytest.mark.parametrize(
    "teams, message",
    [
        (("A", "B"), "exactly 6"),
        (("A", "B", "C", "D", "E", "E"), "unique"),
        (("A", "B", "C", "D", "E", ""), "non-empty"),
    ],
)
def test_schedule_rejects_invalid_leagues(teams: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        generate_schedule(teams, seed=1)


def test_standings_accumulate_counts_and_apply_every_tie_break_in_order() -> None:
    # E is 4-0. A/B/C/D are each 1-1: A wins run differential, B then wins
    # runs scored, and C precedes D by TeamID with otherwise identical records.
    results = (
        GameResult(1, "F", "A", 0, 10),
        GameResult(2, "A", "E", 0, 1),
        GameResult(3, "F", "B", 2, 6),
        GameResult(4, "B", "E", 0, 1),
        GameResult(5, "F", "C", 1, 5),
        GameResult(6, "C", "E", 0, 1),
        GameResult(7, "F", "D", 1, 5),
        GameResult(8, "D", "E", 0, 1),
    )
    standings = Standings.from_results(TEAMS, results)
    assert [row.team_id for row in standings.rows] == ["E", "A", "B", "C", "D", "F"]
    assert standings.results_count == len(results)
    assert sum(row.wins for row in standings.rows) == len(results)
    assert sum(row.losses for row in standings.rows) == len(results)
    assert sum(row.runs_scored for row in standings.rows) == sum(
        row.runs_allowed for row in standings.rows
    )
    assert standings.rows[0].winning_percentage == 1.0
    assert standings.rows[0].games_behind == 0.0
    assert standings.rows[1].run_differential == 9
    assert standings.rows[2].run_differential == standings.rows[3].run_differential == 3
    assert standings.rows[2].runs_scored > standings.rows[3].runs_scored
    assert standings.rows[3].run_differential == standings.rows[4].run_differential
    assert standings.rows[3].runs_scored == standings.rows[4].runs_scored


def test_games_behind_and_empty_standings_are_exact() -> None:
    empty = Standings.from_results(TEAMS, ())
    assert [row.team_id for row in empty.rows] == list(TEAMS)
    assert all(row.winning_percentage == 0.0 and row.games_behind == 0.0 for row in empty.rows)

    standings = Standings.from_results(TEAMS, (GameResult(1, "B", "A", 0, 1),))
    rows = {row.team_id: row for row in standings.rows}
    assert rows["A"].games_behind == 0.0
    assert rows["C"].games_behind == 0.5
    assert rows["B"].games_behind == 1.0


def test_full_schedule_results_preserve_league_conservation() -> None:
    schedule = generate_schedule(TEAMS, seed=7)
    results = tuple(
        GameResult(
            game.game_number,
            game.away_team_id,
            game.home_team_id,
            away_runs=game.game_number % 5,
            home_runs=(game.game_number % 5) + 1,
        )
        for game in schedule
    )
    standings = Standings.from_results(TEAMS, results)
    assert standings.results_count == LEAGUE_GAMES
    assert all(row.games == TEAM_GAMES for row in standings.rows)
    assert sum(row.wins for row in standings.rows) == LEAGUE_GAMES
    assert sum(row.losses for row in standings.rows) == LEAGUE_GAMES
    assert sum(row.runs_scored for row in standings.rows) == sum(
        row.runs_allowed for row in standings.rows
    )


@pytest.mark.parametrize(
    "result, message",
    [
        (lambda: GameResult(0, "A", "B", 1, 0), "positive"),
        (lambda: GameResult(1, "A", "A", 1, 0), "itself"),
        (lambda: GameResult(1, "A", "B", -1, 0), "negative"),
        (lambda: GameResult(1, "A", "B", 1, 1), "tie"),
    ],
)
def test_game_result_validation(result: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        result()  # type: ignore[operator]


def test_standings_reject_duplicate_games_and_unknown_teams() -> None:
    duplicate = (
        GameResult(1, "A", "B", 1, 0),
        GameResult(1, "C", "D", 2, 0),
    )
    with pytest.raises(ValueError, match="duplicate"):
        Standings.from_results(TEAMS, duplicate)
    with pytest.raises(ValueError, match="outside"):
        Standings.from_results(TEAMS, (GameResult(1, "A", "Z", 1, 0),))
