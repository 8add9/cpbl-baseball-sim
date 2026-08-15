"""Authoritative, immutable aggregate for the first Career v4 weekly slice.

This intentionally wraps the proven v3 player/stat state.  It does not claim that
offseason, contracts, injuries or game participation are complete Career v4 features.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .approach import BattingApproach
from .calendar_v4 import (
    CALENDAR_MODEL_VERSION,
    CareerCalendar,
    PlannedAction,
    WeekPlan,
    build_career_calendar,
    plan_week,
)
from .condition import CareerActivity, CareerCondition, apply_activity
from .condition import advance_day as age_condition
from .lifecycle_v4 import (
    LIFECYCLE_MODEL_VERSION,
    CareerLifecycle,
    CareerPhase,
    acknowledge_post_game,
    advance_week,
    begin_day,
    complete_day_action,
    finish_game,
    reach_player_pa,
    resolve_player_pa,
    submit_week_plan,
)
from .lifecycle_v4 import (
    advance_day as advance_lifecycle_day,
)
from .models import CareerState
from .simulation import (
    BaserunningStrategy,
    advance_season,
    play_game,
    prepare_player_pa,
    resolve_prepared_player_pa,
)
from .team_status import TeamStanding
from .weekly import (
    WEEKLY_ACTION_POINTS,
    WeeklyDevelopment,
    apply_weekly_action,
    archetype_potential_traits,
)

CAREER_AGGREGATE_SCHEMA_VERSION = 4
CAREER_AGGREGATE_MODEL_VERSION = "batter-career-aggregate-v0.1"


@dataclass(frozen=True, slots=True)
class CareerAggregateV4:
    career: CareerState
    calendar: CareerCalendar
    lifecycle: CareerLifecycle
    weekly_development: WeeklyDevelopment
    condition: CareerCondition
    team_standing: TeamStanding
    current_plan: WeekPlan | None = None
    migrated_from_schema: int | None = None
    schema_version: int = CAREER_AGGREGATE_SCHEMA_VERSION
    model_version: str = CAREER_AGGREGATE_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAREER_AGGREGATE_SCHEMA_VERSION:
            raise ValueError("unsupported Career aggregate schema")
        if self.model_version != CAREER_AGGREGATE_MODEL_VERSION:
            raise ValueError("unsupported Career aggregate model")
        if self.calendar.model_version != CALENDAR_MODEL_VERSION:
            raise ValueError("unsupported calendar model")
        if self.lifecycle.model_version != LIFECYCLE_MODEL_VERSION:
            raise ValueError("unsupported lifecycle model")
        if self.weekly_development.week != self.lifecycle.week:
            raise ValueError("weekly development and lifecycle weeks differ")
        if self.current_plan is not None and self.current_plan.week != self.lifecycle.week:
            raise ValueError("week plan and lifecycle weeks differ")
        if self.lifecycle.phase is CareerPhase.WEEK_PLANNING and self.current_plan is not None:
            raise ValueError("a planning phase cannot already have a submitted plan")


def migrate_v3_career(
    career: CareerState,
    *,
    team_id: str,
    opponent_ids: tuple[str, ...],
) -> CareerAggregateV4:
    """Lift a v3 save at a completed-game boundary into the v4 weekly aggregate."""

    if career.active_game is not None:
        raise ValueError("a v3 career with an active game cannot be migrated")
    if career.origin.season_games != 120:
        raise ValueError("Career v4 migration requires a 120-game season")
    if career.games_played not in {120} and career.games_played % 4:
        raise ValueError("Career v4 migration requires a completed weekly game boundary")
    calendar = build_career_calendar(
        team_id=team_id, opponent_ids=opponent_ids, seed=career.origin.seed
    )
    if career.games_played == 120:
        lifecycle = CareerLifecycle(
            season_number=len(career.completed_seasons) + 1,
            week=30,
            weekday=7,
            phase=CareerPhase.SEASON_REVIEW,
        )
        week = 30
    else:
        week = career.games_played // 4 + 1
        lifecycle = CareerLifecycle(
            season_number=len(career.completed_seasons) + 1,
            week=week,
            phase=CareerPhase.WEEK_PLANNING,
        )
    return CareerAggregateV4(
        career=career,
        calendar=calendar,
        lifecycle=lifecycle,
        weekly_development=WeeklyDevelopment(week=week),
        condition=CareerCondition(),
        team_standing=TeamStanding(),
        migrated_from_schema=career.schema_version,
    )


def create_v4_aggregate(
    career: CareerState,
    *,
    team_id: str,
    opponent_ids: tuple[str, ...],
) -> CareerAggregateV4:
    """Create a native v4 aggregate while reusing the validated player-state constructor."""

    return replace(
        migrate_v3_career(career, team_id=team_id, opponent_ids=opponent_ids),
        migrated_from_schema=None,
    )


def submit_plan(
    aggregate: CareerAggregateV4, actions: tuple[PlannedAction, ...]
) -> CareerAggregateV4:
    plan = plan_week(aggregate.calendar, aggregate.lifecycle.week, actions)
    lifecycle = submit_week_plan(aggregate.lifecycle, plan)
    return replace(aggregate, lifecycle=lifecycle, current_plan=plan)


def _reset_development_for_week(development: WeeklyDevelopment, week: int) -> WeeklyDevelopment:
    return replace(
        development,
        week=week,
        action_points=WEEKLY_ACTION_POINTS,
        contact_repeats=0,
        power_repeats=0,
        eye_repeats=0,
        speed_repeats=0,
    )


def _advance_after_completed_day(
    aggregate: CareerAggregateV4,
    *,
    lifecycle: CareerLifecycle,
    condition: CareerCondition,
) -> CareerAggregateV4:
    condition = age_condition(condition)
    lifecycle = advance_lifecycle_day(lifecycle)
    development = aggregate.weekly_development
    current_plan: WeekPlan | None = aggregate.current_plan
    if lifecycle.phase is CareerPhase.WEEK_REVIEW:
        lifecycle = advance_week(lifecycle)
        current_plan = None
        if lifecycle.phase is CareerPhase.WEEK_PLANNING:
            development = _reset_development_for_week(development, lifecycle.week)
    return replace(
        aggregate,
        lifecycle=lifecycle,
        weekly_development=development,
        condition=condition,
        current_plan=current_plan,
    )


def start_interactive_game(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Enter today's game and stop before the created player's first PA."""
    if aggregate.current_plan is None:
        raise ValueError("a week plan must be submitted before starting a game")
    day = aggregate.calendar.week_days(aggregate.lifecycle.week)[aggregate.lifecycle.weekday - 1]
    if not day.is_game_day:
        raise ValueError("today is not a game day")
    lifecycle = begin_day(aggregate.lifecycle, day)
    career = prepare_player_pa(aggregate.career)
    lifecycle = (
        finish_game(lifecycle)
        if career.active_game is None
        else reach_player_pa(lifecycle)
    )
    return replace(aggregate, career=career, lifecycle=lifecycle)


def resolve_interactive_pa(
    aggregate: CareerAggregateV4,
    *,
    approach: BattingApproach,
    baserunning: BaserunningStrategy,
) -> CareerAggregateV4:
    lifecycle = resolve_player_pa(aggregate.lifecycle)
    career = resolve_prepared_player_pa(
        aggregate.career,
        approach=approach,
        context=aggregate.condition,
        baserunning=baserunning,
    )
    lifecycle = (
        finish_game(lifecycle)
        if career.active_game is None
        else reach_player_pa(lifecycle)
    )
    return replace(aggregate, career=career, lifecycle=lifecycle)


def simulate_interactive_game(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Finish an entered game with Normal/Balanced decisions."""
    result = aggregate
    if result.lifecycle.phase is CareerPhase.DAY_READY:
        result = start_interactive_game(result)
    for _ in range(20):
        if result.lifecycle.phase is CareerPhase.POST_GAME:
            return result
        if result.lifecycle.phase is not CareerPhase.PLAYER_PA:
            raise ValueError("the career is not at a playable game phase")
        result = resolve_interactive_pa(
            result,
            approach=BattingApproach.NORMAL,
            baserunning=BaserunningStrategy.BALANCED,
        )
    raise RuntimeError("career game exceeded the player-PA safety limit")


def acknowledge_interactive_game(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    lifecycle = acknowledge_post_game(aggregate.lifecycle)
    condition = apply_activity(aggregate.condition, CareerActivity.STARTER_GAME)
    return _advance_after_completed_day(
        aggregate,
        lifecycle=lifecycle,
        condition=condition,
    )


def advance_one_day(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Resolve exactly the lifecycle cursor day and atomically cross its week boundary."""

    if aggregate.current_plan is None:
        raise ValueError("a week plan must be submitted before advancing a day")
    day = aggregate.calendar.week_days(aggregate.lifecycle.week)[aggregate.lifecycle.weekday - 1]
    lifecycle = begin_day(aggregate.lifecycle, day)
    career = aggregate.career
    development = aggregate.weekly_development
    condition = aggregate.condition
    if day.is_game_day:
        career = play_game(career, plate_appearances=4)
        condition = apply_activity(condition, CareerActivity.STARTER_GAME)
        lifecycle = acknowledge_post_game(finish_game(lifecycle))
    else:
        planned = next(
            (
                item.action
                for item in aggregate.current_plan.actions
                if int(item.weekday) == aggregate.lifecycle.weekday
            ),
            None,
        )
        if planned is not None:
            result = apply_weekly_action(
                development,
                career.scores,
                archetype_potential_traits(career.origin.profile.archetype),
                career.origin.profile.archetype,
                planned,
                age=career.age,
                seed=career.origin.seed,
                fatigue=condition.fatigue,
            )
            development = result.development
            career = replace(career, scores=result.scores)
            condition = replace(
                condition,
                fatigue=min(100.0, max(0.0, condition.fatigue + result.fatigue_delta)),
            )
        else:
            condition = apply_activity(condition, CareerActivity.NONE)
        lifecycle = complete_day_action(lifecycle)
    advanced = replace(
        aggregate,
        career=career,
        lifecycle=lifecycle,
        weekly_development=development,
        condition=condition,
    )
    return _advance_after_completed_day(
        advanced,
        lifecycle=lifecycle,
        condition=condition,
    )


def simulate_current_week(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Finish the current calendar week with the submitted plan (or a rest plan)."""

    result = aggregate
    if result.lifecycle.phase is CareerPhase.WEEK_PLANNING:
        result = submit_plan(result, ())
    if result.lifecycle.phase is not CareerPhase.DAY_READY:
        raise ValueError("the current phase cannot simulate a week")
    starting_week = result.lifecycle.week
    for _ in range(7):
        result = advance_one_day(result)
        if (
            result.lifecycle.week != starting_week
            or result.lifecycle.phase is CareerPhase.SEASON_REVIEW
        ):
            return result
    raise RuntimeError("career week exceeded the seven-day safety limit")


def simulate_regular_season(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Finish the regular season without bypassing calendar or weekly reducers."""

    result = aggregate
    for _ in range(31):
        if result.lifecycle.phase is CareerPhase.SEASON_REVIEW:
            return result
        result = simulate_current_week(result)
    raise RuntimeError("career season exceeded the thirty-week safety limit")


def advance_career_phase(aggregate: CareerAggregateV4) -> CareerAggregateV4:
    """Advance exactly one acknowledged season/offseason phase."""

    lifecycle = aggregate.lifecycle
    if lifecycle.phase is CareerPhase.SEASON_REVIEW:
        from .lifecycle_v4 import acknowledge_season_review

        return replace(aggregate, lifecycle=acknowledge_season_review(lifecycle))
    if lifecycle.phase is CareerPhase.AWARDS:
        from .lifecycle_v4 import acknowledge_awards

        return replace(aggregate, lifecycle=acknowledge_awards(lifecycle))
    if lifecycle.phase is CareerPhase.CONTRACT:
        from .lifecycle_v4 import resolve_contract

        return replace(aggregate, lifecycle=resolve_contract(lifecycle))
    if lifecycle.phase is CareerPhase.OFFSEASON_TRAINING:
        from .lifecycle_v4 import complete_offseason_training

        return replace(aggregate, lifecycle=complete_offseason_training(lifecycle))
    if lifecycle.phase is CareerPhase.READY_NEXT_SEASON:
        from .lifecycle_v4 import start_next_season

        career = advance_season(aggregate.career)
        if career.retired:
            return replace(
                aggregate, career=career, lifecycle=replace(lifecycle, phase=CareerPhase.RETIRED)
            )
        next_lifecycle = start_next_season(lifecycle)
        calendar = build_career_calendar(
            team_id=aggregate.calendar.team_id,
            opponent_ids=aggregate.calendar.opponent_ids,
            seed=career.origin.seed ^ career.season_year,
        )
        return replace(
            aggregate,
            career=career,
            calendar=calendar,
            lifecycle=next_lifecycle,
            weekly_development=_reset_development_for_week(aggregate.weekly_development, 1),
            condition=replace(
                aggregate.condition, fatigue=max(0.0, aggregate.condition.fatigue - 25.0)
            ),
            current_plan=None,
        )
    raise ValueError("the current phase has no season transition")
