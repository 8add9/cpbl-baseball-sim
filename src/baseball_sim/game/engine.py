"""Deterministic transitions for the v0.1 numerical baseball game."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from baseball_sim.simulation.outcomes import Outcome

from .state import GameState, HalfInning, Team


@dataclass(frozen=True, slots=True)
class Transition:
    state: GameState
    outcome: Outcome
    batter: str
    pitcher: str
    runs_scored: int
    inning_ended: bool
    walk_off: bool


def _advance_walk(
    bases: tuple[str | None, str | None, str | None], batter: str
) -> tuple[tuple[str | None, str | None, str | None], int]:
    first, second, third = bases
    runs = 0
    if first is not None:
        if second is not None:
            if third is not None:
                runs = 1
            third = second
        second = first
    first = batter
    return (first, second, third), runs


def _advance_hit(
    bases: tuple[str | None, str | None, str | None], batter: str, bases_awarded: int
) -> tuple[tuple[str | None, str | None, str | None], int]:
    runners = [(index + 1, runner) for index, runner in enumerate(bases) if runner is not None]
    runs = sum(1 for base, _runner in runners if base + bases_awarded >= 4)
    if bases_awarded == 4:
        return (None, None, None), runs + 1
    advanced: list[str | None] = [None, None, None]
    for base, runner in runners:
        destination = base + bases_awarded
        if destination < 4:
            advanced[destination - 1] = runner
    advanced[bases_awarded - 1] = batter
    return (advanced[0], advanced[1], advanced[2]), runs


def _score(state: GameState, runs: int) -> GameState:
    if state.batting_team is Team.AWAY:
        return replace(state, away_score=state.away_score + runs)
    return replace(state, home_score=state.home_score + runs)


def _next_batter(state: GameState) -> GameState:
    if state.batting_team is Team.AWAY:
        return replace(
            state,
            away_lineup_index=(state.away_lineup_index + 1) % len(state.away_lineup),
            plate_appearances=state.plate_appearances + 1,
        )
    return replace(
        state,
        home_lineup_index=(state.home_lineup_index + 1) % len(state.home_lineup),
        plate_appearances=state.plate_appearances + 1,
    )


def _finish(state: GameState, winner: Team) -> GameState:
    return replace(state, finished=True, winner=winner, outs=0, bases=(None, None, None))


def _end_half(state: GameState) -> GameState:
    if state.half is HalfInning.TOP:
        if state.inning >= 9 and state.home_score > state.away_score:
            return _finish(state, Team.HOME)
        return replace(state, half=HalfInning.BOTTOM, outs=0, bases=(None, None, None))
    if state.inning >= 9 and state.home_score != state.away_score:
        winner = Team.HOME if state.home_score > state.away_score else Team.AWAY
        return _finish(state, winner)
    return replace(
        state,
        inning=state.inning + 1,
        half=HalfInning.TOP,
        outs=0,
        bases=(None, None, None),
    )


def apply_outcome(state: GameState, outcome: Outcome) -> Transition:
    """Apply one PA using documented deterministic station-to-station advancement."""
    if state.finished:
        raise ValueError("cannot apply an outcome to a finished game")
    batter = state.batter
    pitcher = state.pitcher
    before_half = (state.inning, state.half)
    runs = 0
    third_out = False

    if outcome in (Outcome.SO, Outcome.OUT):
        third_out = state.outs == 2
        if not third_out:
            state = replace(state, outs=state.outs + 1)
    elif outcome in (Outcome.BB, Outcome.HBP):
        bases, runs = _advance_walk(state.bases, batter)
        state = replace(state, bases=bases)
    else:
        bases_awarded = {
            Outcome.SINGLE: 1,
            Outcome.DOUBLE: 2,
            Outcome.TRIPLE: 3,
            Outcome.HR: 4,
        }[outcome]
        bases, runs = _advance_hit(state.bases, batter, bases_awarded)
        state = replace(state, bases=bases)

    if (
        runs > 0
        and outcome is not Outcome.HR
        and state.half is HalfInning.BOTTOM
        and state.inning >= 9
    ):
        runs_needed = state.away_score - state.home_score + 1
        if 0 < runs_needed <= runs:
            runs = runs_needed
    state = _next_batter(_score(state, runs))
    walk_off = (
        state.half is HalfInning.BOTTOM
        and state.inning >= 9
        and state.home_score > state.away_score
    )
    if walk_off:
        state = _finish(state, Team.HOME)
    elif third_out:
        state = _end_half(state)
    inning_ended = before_half != (state.inning, state.half) or state.finished
    return Transition(state, outcome, batter, pitcher, runs, inning_ended, walk_off)


def replay(initial: GameState, outcomes: Iterable[Outcome]) -> GameState:
    state = initial
    for outcome in outcomes:
        if state.finished:
            break
        state = apply_outcome(state, outcome).state
    return state
