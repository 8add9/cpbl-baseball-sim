from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from baseball_sim.career.calendar_v4 import build_career_calendar, plan_week
from baseball_sim.career.lifecycle_v4 import (
    LIFECYCLE_MODEL_VERSION,
    CareerLifecycle,
    CareerPhase,
    acknowledge_awards,
    acknowledge_post_game,
    acknowledge_season_review,
    advance_day,
    advance_week,
    begin_day,
    complete_day_action,
    complete_offseason_training,
    finish_game,
    reach_player_pa,
    resolve_contract,
    resolve_player_pa,
    retire,
    start_next_season,
    submit_week_plan,
)


def test_complete_week_follows_only_legal_game_and_non_game_paths() -> None:
    calendar = build_career_calendar(
        team_id="A", opponent_ids=("B", "C", "D", "E", "F"), seed=12
    )
    state = submit_week_plan(CareerLifecycle(), plan_week(calendar, 1, ()))
    for day in calendar.week_days(1):
        state = begin_day(state, day)
        if day.is_game_day:
            state = reach_player_pa(state)
            state = resolve_player_pa(state)
            state = finish_game(state)
            state = acknowledge_post_game(state)
        else:
            state = complete_day_action(state)
        state = advance_day(state)
    assert state.phase is CareerPhase.WEEK_REVIEW
    assert state.weekday == 7
    state = advance_week(state)
    assert (state.week, state.weekday, state.phase) == (2, 1, CareerPhase.WEEK_PLANNING)


def test_week_30_transitions_through_offseason_and_starts_fresh_season() -> None:
    state = CareerLifecycle(week=30, weekday=7, phase=CareerPhase.WEEK_REVIEW)
    state = advance_week(state)
    assert state.phase is CareerPhase.SEASON_REVIEW
    state = acknowledge_season_review(state)
    state = acknowledge_awards(state)
    state = resolve_contract(state)
    state = complete_offseason_training(state)
    state = start_next_season(state)
    assert state == CareerLifecycle(season_number=2)
    assert state.model_version == LIFECYCLE_MODEL_VERSION


def test_illegal_skips_mismatched_cursor_and_retired_terminal_are_rejected() -> None:
    state = CareerLifecycle()
    with pytest.raises(ValueError, match="cannot perform"):
        finish_game(state)
    calendar = build_career_calendar(
        team_id="A", opponent_ids=("B", "C", "D", "E", "F"), seed=3
    )
    ready = submit_week_plan(state, plan_week(calendar, 1, ()))
    with pytest.raises(ValueError, match="cursor"):
        begin_day(ready, calendar.week_days(2)[0])
    retired = retire(CareerLifecycle(week=30, weekday=7, phase=CareerPhase.SEASON_REVIEW))
    assert retired.phase is CareerPhase.RETIRED
    with pytest.raises(ValueError, match="cannot perform"):
        start_next_season(retired)
    with pytest.raises(ValueError, match="seven completed days"):
        CareerLifecycle(phase=CareerPhase.WEEK_REVIEW)


def test_state_is_immutable_and_player_pa_must_resolve_before_game_can_finish() -> None:
    state = CareerLifecycle(phase=CareerPhase.PLAYER_PA)
    with pytest.raises(ValueError, match="cannot perform"):
        finish_game(state)
    with pytest.raises(FrozenInstanceError):
        state.week = 2  # type: ignore[misc]
