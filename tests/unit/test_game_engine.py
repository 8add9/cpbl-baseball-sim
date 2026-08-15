from __future__ import annotations

from dataclasses import replace

import pytest

from baseball_sim.game import GameState, HalfInning, Team, apply_outcome, apply_steal, replay
from baseball_sim.simulation.outcomes import Outcome


@pytest.fixture
def game() -> GameState:
    return GameState(
        away_lineup=tuple(f"A{index}" for index in range(1, 10)),
        home_lineup=tuple(f"H{index}" for index in range(1, 10)),
        away_pitcher="AP",
        home_pitcher="HP",
    )


def test_three_outs_switch_half_and_clear_bases(game: GameState) -> None:
    state = replace(game, bases=("A3", None, None))
    state = replay(state, [Outcome.SO, Outcome.OUT, Outcome.SO])
    assert state.inning == 1
    assert state.half is HalfInning.BOTTOM
    assert state.outs == 0
    assert state.bases == (None, None, None)
    assert state.away_lineup_index == 3


def test_lineup_wraps_and_pitcher_is_defensive_team_pitcher(game: GameState) -> None:
    first = apply_outcome(game, Outcome.OUT)
    second = apply_outcome(first.state, Outcome.OUT)
    third = apply_outcome(second.state, Outcome.OUT)
    assert (first.batter, second.batter, third.batter) == ("A1", "A2", "A3")
    assert first.pitcher == "HP"
    assert third.state.batter == "H1"
    assert third.state.pitcher == "AP"


def test_ninth_lineup_slot_wraps_to_leadoff(game: GameState) -> None:
    ninth = replace(game, away_lineup_index=8)
    state = apply_outcome(ninth, Outcome.SINGLE).state
    assert state.away_lineup_index == 0


def test_walk_advances_only_forced_runners(game: GameState) -> None:
    forced = replace(game, bases=("R1", "R2", "R3"))
    transition = apply_outcome(forced, Outcome.BB)
    assert transition.runs_scored == 1
    assert transition.state.bases == ("A1", "R1", "R2")
    assert transition.state.away_score == 1

    not_forced = replace(game, bases=(None, "R2", "R3"))
    transition = apply_outcome(not_forced, Outcome.HBP)
    assert transition.runs_scored == 0
    assert transition.state.bases == ("A1", "R2", "R3")


@pytest.mark.parametrize(
    ("outcome", "expected_bases", "runs"),
    [
        (Outcome.SINGLE, ("A1", "R1", "R2"), 1),
        (Outcome.DOUBLE, (None, "A1", "R1"), 2),
        (Outcome.TRIPLE, (None, None, "A1"), 3),
        (Outcome.HR, (None, None, None), 4),
    ],
)
def test_station_to_station_hit_advancement(
    game: GameState,
    outcome: Outcome,
    expected_bases: tuple[str | None, str | None, str | None],
    runs: int,
) -> None:
    loaded = replace(game, bases=("R1", "R2", "R3"))
    transition = apply_outcome(loaded, outcome)
    assert transition.runs_scored == runs
    assert transition.state.bases == expected_bases
    assert transition.state.away_score == runs


def test_home_lead_after_top_ninth_skips_bottom(game: GameState) -> None:
    top_ninth = replace(
        game,
        inning=9,
        half=HalfInning.TOP,
        outs=2,
        home_score=3,
        away_score=2,
    )
    transition = apply_outcome(top_ninth, Outcome.OUT)
    assert transition.state.finished
    assert transition.state.winner is Team.HOME


def test_tied_bottom_ninth_advances_to_extra_innings(game: GameState) -> None:
    bottom_ninth = replace(
        game,
        inning=9,
        half=HalfInning.BOTTOM,
        outs=2,
        home_score=2,
        away_score=2,
    )
    state = apply_outcome(bottom_ninth, Outcome.SO).state
    assert not state.finished
    assert state.inning == 10
    assert state.half is HalfInning.TOP


def test_bottom_ninth_scoring_play_is_walk_off(game: GameState) -> None:
    bottom_ninth = replace(
        game,
        inning=9,
        half=HalfInning.BOTTOM,
        home_score=2,
        away_score=2,
        bases=(None, None, "H3"),
    )
    transition = apply_outcome(bottom_ninth, Outcome.SINGLE)
    assert transition.walk_off
    assert transition.state.finished
    assert transition.state.winner is Team.HOME
    assert transition.state.home_score == 3


def test_non_homer_walk_off_credits_only_runs_needed(game: GameState) -> None:
    tied_loaded = replace(
        game,
        inning=10,
        half=HalfInning.BOTTOM,
        home_score=4,
        away_score=4,
        bases=("R1", "R2", "R3"),
    )
    transition = apply_outcome(tied_loaded, Outcome.DOUBLE)
    assert transition.runs_scored == 1
    assert transition.state.home_score == 5

    down_one = replace(tied_loaded, home_score=3, bases=(None, "R2", "R3"))
    transition = apply_outcome(down_one, Outcome.DOUBLE)
    assert transition.runs_scored == 2
    assert transition.state.home_score == 5


def test_walk_off_home_run_credits_every_runner(game: GameState) -> None:
    bottom_ninth = replace(
        game,
        inning=9,
        half=HalfInning.BOTTOM,
        home_score=1,
        away_score=3,
        bases=("H1", "H2", "H3"),
    )
    transition = apply_outcome(bottom_ninth, Outcome.HR)
    assert transition.runs_scored == 4
    assert transition.state.home_score == 5


def test_away_win_is_recorded_after_bottom_half(game: GameState) -> None:
    bottom_tenth = replace(
        game,
        inning=10,
        half=HalfInning.BOTTOM,
        outs=2,
        away_score=5,
        home_score=4,
    )
    state = apply_outcome(bottom_tenth, Outcome.SO).state
    assert state.finished
    assert state.winner is Team.AWAY


def test_pitcher_change_is_explicit_and_immutable(game: GameState) -> None:
    changed = game.with_pitcher(Team.HOME, "HP2")
    assert game.home_pitcher == "HP"
    assert changed.home_pitcher == "HP2"
    assert apply_outcome(changed, Outcome.SO).pitcher == "HP2"
    with pytest.raises(ValueError, match="fielding"):
        game.with_pitcher(Team.AWAY, "AP2")


def test_finished_game_rejects_more_outcomes(game: GameState) -> None:
    finished = replace(game, finished=True, winner=Team.HOME)
    with pytest.raises(ValueError, match="finished"):
        apply_outcome(finished, Outcome.HR)


def test_replay_is_deterministic(game: GameState) -> None:
    outcomes = [Outcome.BB, Outcome.DOUBLE, Outcome.SO, Outcome.OUT, Outcome.HR, Outcome.OUT]
    assert replay(game, outcomes) == replay(game, outcomes)


def test_steal_is_a_non_pa_transition_and_caught_stealing_can_end_half(
    game: GameState,
) -> None:
    runner = replace(game, bases=("A1", None, None), plate_appearances=7)
    stolen = apply_steal(runner, "A1", 1, success=True)
    assert stolen.state.bases == (None, "A1", None)
    assert stolen.state.plate_appearances == 7
    caught = apply_steal(replace(runner, outs=2), "A1", 1, success=False)
    assert caught.inning_ended
    assert caught.state.half is HalfInning.BOTTOM
    assert caught.state.plate_appearances == 7
