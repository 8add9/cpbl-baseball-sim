from __future__ import annotations

import pytest

from baseball_sim.career.aggregate_v4 import advance_one_day, migrate_v3_career, submit_plan
from baseball_sim.career.calendar_v4 import PlannedAction
from baseball_sim.career.models import BatterArchetype, Handedness, create_career
from baseball_sim.career.persistence_v4 import (
    CareerV4ConflictError,
    SqliteCareerV4Repository,
    aggregate_from_dict,
    aggregate_to_dict,
)
from baseball_sim.career.simulation import simulate_games
from baseball_sim.career.weekly import WeeklyAction

OPPONENTS = ("B", "C", "D", "E", "F")


def _aggregate(player_id: str = "player"):
    legacy = create_career(
        player_id=player_id,
        name="測試球員",
        position="SS",
        bats=Handedness.RIGHT,
        throws=Handedness.RIGHT,
        archetype=BatterArchetype.CONTACT,
        age=18,
        season_year=2026,
        seed=77,
        season_games=120,
    )
    return migrate_v3_career(legacy, team_id="A", opponent_ids=OPPONENTS)


def test_aggregate_roundtrip_contains_all_authoritative_weekly_components() -> None:
    aggregate = _aggregate()
    open_day = next(
        day.weekday for day in aggregate.calendar.week_days(1) if not day.is_game_day
    )
    aggregate = submit_plan(
        aggregate, (PlannedAction(open_day, WeeklyAction.CONTACT),)
    )
    loaded = aggregate_from_dict(aggregate_to_dict(aggregate))
    assert loaded == aggregate
    assert loaded.current_plan is not None
    assert loaded.condition == aggregate.condition
    assert loaded.team_standing == aggregate.team_standing
    assert loaded.weekly_development == aggregate.weekly_development


def test_repository_cas_idempotency_and_restart(tmp_path) -> None:
    database = tmp_path / "career-v4.sqlite3"
    repository = SqliteCareerV4Repository(database)
    record = repository.create(
        operation_id="create",
        expected_revision=0,
        request_payload={"seed": 77},
        aggregate_factory=lambda career_id: _aggregate(career_id),
    )
    duplicate = repository.create(
        operation_id="create",
        expected_revision=0,
        request_payload={"seed": 77},
        aggregate_factory=lambda career_id: _aggregate(career_id),
    )
    assert duplicate == record
    planned = repository.mutate(
        career_id=record.career_id,
        operation_id="plan",
        action="plan-week",
        expected_revision=1,
        request_payload={"actions": []},
        operation=lambda aggregate: submit_plan(aggregate, ()),
    )
    advanced = repository.mutate(
        career_id=record.career_id,
        operation_id="day",
        action="advance-day",
        expected_revision=2,
        request_payload={},
        operation=advance_one_day,
    )
    assert SqliteCareerV4Repository(database).get(record.career_id) == advanced
    assert planned.revision == 2 and advanced.revision == 3
    with pytest.raises(CareerV4ConflictError, match="current is 3"):
        repository.mutate(
            career_id=record.career_id,
            operation_id="stale",
            action="advance-day",
            expected_revision=2,
            request_payload={},
            operation=advance_one_day,
        )


def test_seven_daily_commands_are_the_only_week_boundary_and_play_four_games() -> None:
    aggregate = submit_plan(_aggregate(), ())
    for _day in range(7):
        aggregate = advance_one_day(aggregate)
    assert aggregate.lifecycle.week == 2
    assert aggregate.lifecycle.weekday == 1
    assert aggregate.lifecycle.phase.value == "week_planning"
    assert aggregate.career.games_played == 4
    assert aggregate.current_plan is None
    assert aggregate.weekly_development.week == 2
    with pytest.raises(ValueError, match="week plan"):
        advance_one_day(aggregate)


def test_v3_migration_rejects_partial_week() -> None:
    aggregate = _aggregate()
    partial_week = simulate_games(aggregate.career, 1)
    with pytest.raises(ValueError, match="weekly game boundary"):
        migrate_v3_career(partial_week, team_id="A", opponent_ids=OPPONENTS)


def test_planned_training_applies_its_fatigue_delta_exactly_once() -> None:
    aggregate = _aggregate()
    open_day = next(
        day.weekday for day in aggregate.calendar.week_days(1) if not day.is_game_day
    )
    aggregate = submit_plan(
        aggregate, (PlannedAction(open_day, WeeklyAction.CONTACT),)
    )
    while aggregate.lifecycle.weekday < int(open_day):
        aggregate = advance_one_day(aggregate)
    before = aggregate.condition.fatigue
    aggregate = advance_one_day(aggregate)
    # Focused training adds 8, then ordinary end-of-day recovery removes 2.
    assert aggregate.condition.fatigue == before + 6
