"""Deterministic Career v4 season calendar and weekly action planning."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

from .weekly import ACTION_COST, WEEKLY_ACTION_POINTS, WeeklyAction

CALENDAR_MODEL_VERSION = "career-calendar-v0.1"
REGULAR_SEASON_WEEKS = 30
GAMES_PER_WEEK = 4
REGULAR_SEASON_GAMES = REGULAR_SEASON_WEEKS * GAMES_PER_WEEK
DAYS_PER_WEEK = 7


class Weekday(IntEnum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


@dataclass(frozen=True, slots=True)
class ScheduledGame:
    game_number: int
    week: int
    weekday: Weekday
    opponent_id: str
    is_home: bool


@dataclass(frozen=True, slots=True)
class CalendarDay:
    week: int
    weekday: Weekday
    game: ScheduledGame | None = None

    @property
    def is_game_day(self) -> bool:
        return self.game is not None


@dataclass(frozen=True, slots=True)
class CareerCalendar:
    team_id: str
    seed: int
    opponent_ids: tuple[str, ...]
    days: tuple[CalendarDay, ...]
    model_version: str = CALENDAR_MODEL_VERSION

    def week_days(self, week: int) -> tuple[CalendarDay, ...]:
        if not 1 <= week <= REGULAR_SEASON_WEEKS:
            raise ValueError("week must be between 1 and 30")
        start = (week - 1) * DAYS_PER_WEEK
        return self.days[start : start + DAYS_PER_WEEK]

    @property
    def games(self) -> tuple[ScheduledGame, ...]:
        return tuple(day.game for day in self.days if day.game is not None)


@dataclass(frozen=True, slots=True)
class PlannedAction:
    weekday: Weekday
    action: WeeklyAction


@dataclass(frozen=True, slots=True)
class WeekPlan:
    week: int
    actions: tuple[PlannedAction, ...]
    action_points_used: int
    action_points_available: int = WEEKLY_ACTION_POINTS
    model_version: str = CALENDAR_MODEL_VERSION

    @property
    def action_points_remaining(self) -> int:
        return self.action_points_available - self.action_points_used


def _digest(seed: int, *parts: object) -> bytes:
    value = ":".join((str(seed), *(str(part) for part in parts)))
    return hashlib.blake2b(value.encode("utf-8"), digest_size=16).digest()


def _ordered(seed: int, scope: object, values: Iterable[str | Weekday]) -> list[str | Weekday]:
    return sorted(values, key=lambda value: _digest(seed, scope, value))


def build_career_calendar(
    *, team_id: str, opponent_ids: tuple[str, ...], seed: int
) -> CareerCalendar:
    """Build an identical schedule for identical inputs, independent of process RNG state."""

    if not team_id.strip():
        raise ValueError("team_id must not be blank")
    if len(opponent_ids) != 5 or len(set(opponent_ids)) != 5:
        raise ValueError("a six-team calendar requires exactly five unique opponents")
    if team_id in opponent_ids or any(not opponent.strip() for opponent in opponent_ids):
        raise ValueError("opponents must be non-blank and must exclude team_id")

    # Twenty-four deterministic opponent cycles give each opponent exactly 24 games.
    opponents: list[str] = []
    for cycle in range(24):
        opponents.extend(str(item) for item in _ordered(seed, f"opponents:{cycle}", opponent_ids))

    opponent_appearances = dict.fromkeys(opponent_ids, 0)
    days: list[CalendarDay] = []
    game_number = 0
    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        selected = set(_ordered(seed, f"game-days:{week}", tuple(Weekday))[:GAMES_PER_WEEK])
        for weekday in Weekday:
            if weekday not in selected:
                days.append(CalendarDay(week=week, weekday=weekday))
                continue
            opponent = opponents[game_number]
            appearance = opponent_appearances[opponent]
            opponent_appearances[opponent] = appearance + 1
            game_number += 1
            game = ScheduledGame(
                game_number=game_number,
                week=week,
                weekday=weekday,
                opponent_id=opponent,
                is_home=appearance % 2 == 0,
            )
            days.append(CalendarDay(week=week, weekday=weekday, game=game))

    return CareerCalendar(
        team_id=team_id,
        seed=seed,
        opponent_ids=opponent_ids,
        days=tuple(days),
    )


def plan_week(
    calendar: CareerCalendar, week: int, actions: Iterable[PlannedAction]
) -> WeekPlan:
    """Validate and freeze a weekly plan; game days cannot also hold a player action."""

    week_days = calendar.week_days(week)
    action_tuple = tuple(actions)
    weekdays = [planned.weekday for planned in action_tuple]
    if len(weekdays) != len(set(weekdays)):
        raise ValueError("at most one action may be assigned to a day")
    game_days = {day.weekday for day in week_days if day.is_game_day}
    if game_days.intersection(weekdays):
        raise ValueError("an action cannot be assigned on a scheduled game day")
    used = sum(ACTION_COST[planned.action] for planned in action_tuple)
    if used > WEEKLY_ACTION_POINTS:
        raise ValueError("weekly action-point budget exceeded")
    return WeekPlan(week=week, actions=action_tuple, action_points_used=used)
