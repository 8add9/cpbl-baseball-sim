"""Immutable Career v4 weekly/season phase state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from .calendar_v4 import DAYS_PER_WEEK, REGULAR_SEASON_WEEKS, CalendarDay, WeekPlan

LIFECYCLE_MODEL_VERSION = "career-lifecycle-v0.1"


class CareerPhase(StrEnum):
    WEEK_PLANNING = "week_planning"
    DAY_READY = "day_ready"
    DAY_ACTION = "day_action"
    GAME = "game"
    PLAYER_PA = "player_pa"
    BETWEEN_PLAYER_PA = "between_player_pa"
    POST_GAME = "post_game"
    DAY_COMPLETE = "day_complete"
    WEEK_REVIEW = "week_review"
    SEASON_REVIEW = "season_review"
    AWARDS = "awards"
    CONTRACT = "contract"
    OFFSEASON_TRAINING = "offseason_training"
    READY_NEXT_SEASON = "ready_next_season"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class CareerLifecycle:
    season_number: int = 1
    week: int = 1
    weekday: int = 1
    phase: CareerPhase = CareerPhase.WEEK_PLANNING
    model_version: str = LIFECYCLE_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.season_number < 1:
            raise ValueError("season_number must be positive")
        if not 1 <= self.week <= REGULAR_SEASON_WEEKS:
            raise ValueError("week must be between 1 and 30")
        if not 1 <= self.weekday <= DAYS_PER_WEEK:
            raise ValueError("weekday must be between 1 and 7")
        if self.phase is CareerPhase.WEEK_PLANNING and self.weekday != 1:
            raise ValueError("week planning must start on weekday 1")
        if self.phase in {
            CareerPhase.WEEK_REVIEW,
            CareerPhase.SEASON_REVIEW,
            CareerPhase.AWARDS,
            CareerPhase.CONTRACT,
            CareerPhase.OFFSEASON_TRAINING,
            CareerPhase.READY_NEXT_SEASON,
        } and self.weekday != DAYS_PER_WEEK:
            raise ValueError("week and season boundaries require seven completed days")


def _require(state: CareerLifecycle, *phases: CareerPhase) -> None:
    if state.phase not in phases:
        expected = ", ".join(phase.value for phase in phases)
        raise ValueError(f"{state.phase.value} cannot perform this transition; expected {expected}")


def submit_week_plan(state: CareerLifecycle, plan: WeekPlan) -> CareerLifecycle:
    _require(state, CareerPhase.WEEK_PLANNING)
    if plan.week != state.week:
        raise ValueError("plan week does not match lifecycle week")
    return replace(state, phase=CareerPhase.DAY_READY, weekday=1)


def begin_day(state: CareerLifecycle, day: CalendarDay) -> CareerLifecycle:
    _require(state, CareerPhase.DAY_READY)
    if day.week != state.week or int(day.weekday) != state.weekday:
        raise ValueError("calendar day does not match lifecycle cursor")
    phase = CareerPhase.GAME if day.is_game_day else CareerPhase.DAY_ACTION
    return replace(state, phase=phase)


def complete_day_action(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.DAY_ACTION)
    return replace(state, phase=CareerPhase.DAY_COMPLETE)


def reach_player_pa(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.GAME, CareerPhase.BETWEEN_PLAYER_PA)
    return replace(state, phase=CareerPhase.PLAYER_PA)


def resolve_player_pa(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.PLAYER_PA)
    return replace(state, phase=CareerPhase.BETWEEN_PLAYER_PA)


def finish_game(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.GAME, CareerPhase.BETWEEN_PLAYER_PA)
    return replace(state, phase=CareerPhase.POST_GAME)


def acknowledge_post_game(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.POST_GAME)
    return replace(state, phase=CareerPhase.DAY_COMPLETE)


def advance_day(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.DAY_COMPLETE)
    if state.weekday == DAYS_PER_WEEK:
        return replace(state, phase=CareerPhase.WEEK_REVIEW)
    return replace(state, weekday=state.weekday + 1, phase=CareerPhase.DAY_READY)


def advance_week(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.WEEK_REVIEW)
    if state.week == REGULAR_SEASON_WEEKS:
        return replace(state, phase=CareerPhase.SEASON_REVIEW)
    return replace(state, week=state.week + 1, weekday=1, phase=CareerPhase.WEEK_PLANNING)


def acknowledge_season_review(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.SEASON_REVIEW)
    return replace(state, phase=CareerPhase.AWARDS)


def acknowledge_awards(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.AWARDS)
    return replace(state, phase=CareerPhase.CONTRACT)


def resolve_contract(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.CONTRACT)
    return replace(state, phase=CareerPhase.OFFSEASON_TRAINING)


def complete_offseason_training(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.OFFSEASON_TRAINING)
    return replace(state, phase=CareerPhase.READY_NEXT_SEASON)


def start_next_season(state: CareerLifecycle) -> CareerLifecycle:
    _require(state, CareerPhase.READY_NEXT_SEASON)
    return CareerLifecycle(season_number=state.season_number + 1)


def retire(state: CareerLifecycle) -> CareerLifecycle:
    _require(
        state,
        CareerPhase.SEASON_REVIEW,
        CareerPhase.CONTRACT,
        CareerPhase.OFFSEASON_TRAINING,
        CareerPhase.READY_NEXT_SEASON,
    )
    return replace(state, phase=CareerPhase.RETIRED)
