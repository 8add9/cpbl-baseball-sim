from __future__ import annotations

from collections import Counter
from dataclasses import FrozenInstanceError

import pytest

from baseball_sim.career.calendar_v4 import (
    CALENDAR_MODEL_VERSION,
    REGULAR_SEASON_GAMES,
    REGULAR_SEASON_WEEKS,
    PlannedAction,
    build_career_calendar,
    plan_week,
)
from baseball_sim.career.weekly import WeeklyAction

OPPONENTS = ("B", "C", "D", "E", "F")


def test_calendar_is_deterministic_balanced_and_exactly_120_games() -> None:
    calendar = build_career_calendar(team_id="A", opponent_ids=OPPONENTS, seed=2026)
    assert calendar == build_career_calendar(team_id="A", opponent_ids=OPPONENTS, seed=2026)
    assert calendar != build_career_calendar(team_id="A", opponent_ids=OPPONENTS, seed=2027)
    assert calendar.model_version == CALENDAR_MODEL_VERSION
    assert len(calendar.days) == REGULAR_SEASON_WEEKS * 7
    assert len(calendar.games) == REGULAR_SEASON_GAMES
    assert [game.game_number for game in calendar.games] == list(range(1, 121))
    assert all(
        len([day for day in calendar.week_days(week) if day.is_game_day]) == 4
        for week in range(1, 31)
    )
    assert Counter(game.opponent_id for game in calendar.games) == dict.fromkeys(OPPONENTS, 24)
    for opponent in OPPONENTS:
        games = [game for game in calendar.games if game.opponent_id == opponent]
        assert sum(game.is_home for game in games) == 12


def test_week_plan_enforces_ap_game_days_and_one_action_per_day() -> None:
    calendar = build_career_calendar(team_id="A", opponent_ids=OPPONENTS, seed=9)
    open_days = [day.weekday for day in calendar.week_days(1) if not day.is_game_day]
    plan = plan_week(
        calendar,
        1,
        (
            PlannedAction(open_days[0], WeeklyAction.CONTACT),
            PlannedAction(open_days[1], WeeklyAction.POWER),
        ),
    )
    assert plan.action_points_used == 4
    assert plan.action_points_remaining == 0

    with pytest.raises(ValueError, match="at most one action"):
        plan_week(
            calendar,
            1,
            (
                PlannedAction(open_days[0], WeeklyAction.RECOVERY),
                PlannedAction(open_days[0], WeeklyAction.VIDEO),
            ),
        )
    game_day = next(day.weekday for day in calendar.week_days(1) if day.is_game_day)
    with pytest.raises(ValueError, match="game day"):
        plan_week(calendar, 1, (PlannedAction(game_day, WeeklyAction.RECOVERY),))
    with pytest.raises(ValueError, match="budget"):
        plan_week(
            calendar,
            1,
            (
                PlannedAction(open_days[0], WeeklyAction.CONTACT),
                PlannedAction(open_days[1], WeeklyAction.POWER),
                PlannedAction(open_days[2], WeeklyAction.VIDEO),
            ),
        )


def test_calendar_validation_and_immutability() -> None:
    with pytest.raises(ValueError, match="five unique"):
        build_career_calendar(team_id="A", opponent_ids=("B", "C"), seed=1)
    with pytest.raises(ValueError, match="exclude"):
        build_career_calendar(team_id="A", opponent_ids=("A", "B", "C", "D", "E"), seed=1)
    calendar = build_career_calendar(team_id="A", opponent_ids=OPPONENTS, seed=1)
    with pytest.raises(FrozenInstanceError):
        calendar.seed = 2  # type: ignore[misc]
