"""FastAPI router for the bounded Career v4 weekly slice."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, status

from baseball_sim.career.aggregate_v4 import (
    CareerAggregateV4,
    acknowledge_interactive_game,
    advance_career_phase,
    advance_one_day,
    create_v4_aggregate,
    migrate_v3_career,
    resolve_interactive_pa,
    simulate_current_week,
    simulate_interactive_game,
    simulate_regular_season,
    start_interactive_game,
    submit_plan,
)
from baseball_sim.career.approach import BattingApproach
from baseball_sim.career.calendar_v4 import PlannedAction, Weekday
from baseball_sim.career.lifecycle_v4 import CareerPhase
from baseball_sim.career.models import (
    BatterSkill,
    BattingStats,
    PlateAppearancePlayedEvent,
    create_career,
)
from baseball_sim.career.persistence_v4 import CareerV4Record, SqliteCareerV4Repository
from baseball_sim.career.simulation import BaserunningStrategy

from .career_repository import SqliteCareerRepository
from .career_v4_schemas import (
    AdvanceCareerDayRequest,
    CareerV4ActiveGame,
    CareerV4CalendarDay,
    CareerV4Dashboard,
    CareerV4Skill,
    CareerV4Stats,
    CreateCareerV4Request,
    MigrateCareerV4Request,
    PlanCareerWeekRequest,
    PlannedActionRequest,
    ResolveCareerPARequest,
)


def _dashboard(record: CareerV4Record) -> CareerV4Dashboard:
    aggregate = record.aggregate
    plan = aggregate.current_plan
    career = aggregate.career
    profile = career.origin.profile
    ratings = career.ratings
    displays = ratings.display
    skills: dict[str, CareerV4Skill] = {}
    for index, name in enumerate(("contact", "power", "eye", "speed_proxy")):
        skills[name] = CareerV4Skill(
            score=getattr(career.scores, name),
            rating_raw=getattr(ratings, name),
            rating_display=displays[index],
            xp=aggregate.weekly_development.xp(list(BatterSkill)[index]),
        )
    planned = (
        {} if plan is None else {int(item.weekday): item.action.value for item in plan.actions}
    )
    calendar_days = [
        CareerV4CalendarDay(
            weekday=int(day.weekday),
            is_game_day=day.is_game_day,
            opponent_id=None if day.game is None else day.game.opponent_id,
            is_home=None if day.game is None else day.game.is_home,
            planned_action=planned.get(int(day.weekday)),
        )
        for day in aggregate.calendar.week_days(aggregate.lifecycle.week)
    ]

    def stats(value: BattingStats) -> CareerV4Stats:
        return CareerV4Stats(
            games=value.games,
            pa=value.pa,
            hits=value.hits,
            home_runs=value.home_runs,
            walks=value.walks,
            strikeouts=value.strikeouts,
            runs=value.runs,
            rbi=value.rbi,
            stolen_bases=value.stolen_bases,
            caught_stealing=value.caught_stealing,
            avg=value.avg,
            obp=value.obp,
            slg=value.slg,
            ops=value.ops,
        )

    phase = aggregate.lifecycle.phase
    available = {
        "week_planning": ["plan_week"],
        "day_ready": ["advance_day", "play_game", "simulate_week", "simulate_season"],
        "player_pa": ["resolve_pa", "simulate_game"],
        "post_game": ["acknowledge_game"],
        "season_review": ["advance_phase"],
        "awards": ["advance_phase"],
        "contract": ["advance_phase"],
        "offseason_training": ["advance_phase"],
        "ready_next_season": ["advance_phase"],
        "retired": [],
    }.get(phase.value, ["advance_day"])
    award = None
    boundary_phases = {
        CareerPhase.SEASON_REVIEW,
        CareerPhase.AWARDS,
        CareerPhase.CONTRACT,
        CareerPhase.OFFSEASON_TRAINING,
        CareerPhase.READY_NEXT_SEASON,
    }
    if phase in boundary_phases:
        if career.season_stats.ops >= 0.850:
            award = "年度明星打者"
        elif career.season_stats.pa >= 400:
            award = "一軍完整球季"
        else:
            award = "球季完成"
    active = career.active_game
    last_pa = next(
        (
            event
            for event in reversed(career.events)
            if isinstance(event, PlateAppearancePlayedEvent)
            and event.career_plate_appearance
        ),
        None,
    )
    active_view = None
    if active is not None:
        game = active.game_state
        player = profile.player_id
        active_view = CareerV4ActiveGame(
            inning=game.inning,
            half=game.half.value,
            outs=game.outs,
            bases=(
                game.bases[0] is not None,
                game.bases[1] is not None,
                game.bases[2] is not None,
            ),
            away_score=game.away_score,
            home_score=game.home_score,
            player_on_base=next(
                (index for index, runner in enumerate(game.bases, 1) if runner == player),
                None,
            ),
            last_outcome=None if last_pa is None else last_pa.outcome.value,
            season_game_number=active.game_number,
        )
    return CareerV4Dashboard(
        career_id=record.career_id,
        revision=record.revision,
        autosaved_at=record.autosaved_at,
        persistence_version=record.persistence_version,
        schema_version=aggregate.schema_version,
        model_version=aggregate.model_version,
        migrated_from_schema=aggregate.migrated_from_schema,
        name=profile.name,
        position=profile.position,
        bats=profile.bats.value,
        throws=profile.throws.value,
        archetype=profile.archetype.value,
        age=career.age,
        season_year=aggregate.career.season_year,
        games_played=aggregate.career.games_played,
        week=aggregate.lifecycle.week,
        weekday=aggregate.lifecycle.weekday,
        phase=aggregate.lifecycle.phase.value,
        current_plan=None
        if plan is None
        else [
            PlannedActionRequest(weekday=int(item.weekday), action=item.action)
            for item in plan.actions
        ],
        action_points_remaining=aggregate.weekly_development.action_points,
        fatigue=aggregate.condition.fatigue,
        form=aggregate.condition.form_latent,
        injured=not aggregate.condition.available,
        coach_trust=aggregate.team_standing.coach_trust,
        team_status=aggregate.team_standing.status.value,
        skills=skills,
        season_stats=stats(career.season_stats),
        career_stats=stats(career.career_stats),
        completed_seasons=len(career.completed_seasons),
        calendar_days=calendar_days,
        available_actions=available,
        season_award=award,
        contract_summary=(
            f"{max(1, round(career.season_stats.ops * 3))} 年合約"
            if phase
            in {
                CareerPhase.CONTRACT,
                CareerPhase.OFFSEASON_TRAINING,
                CareerPhase.READY_NEXT_SEASON,
            }
            else None
        ),
        active_game=active_view,
    )


def career_v4_router(
    repository: SqliteCareerV4Repository, legacy_repository: SqliteCareerRepository
) -> APIRouter:
    router = APIRouter(prefix="/api/careers-v4", tags=["career-v4"])

    @router.get("", response_model=list[CareerV4Dashboard])
    def list_endpoint() -> list[CareerV4Dashboard]:
        return [_dashboard(record) for record in repository.list()]

    @router.post("", response_model=CareerV4Dashboard, status_code=status.HTTP_201_CREATED)
    def create_endpoint(request: CreateCareerV4Request) -> CareerV4Dashboard:
        payload = request.model_dump(mode="json")
        record = repository.create(
            operation_id=request.operation_id,
            expected_revision=request.expected_revision,
            request_payload=payload,
            aggregate_factory=lambda career_id: create_v4_aggregate(
                create_career(
                    player_id=career_id,
                    name=request.name,
                    position=request.position,
                    bats=request.bats,
                    throws=request.throws,
                    archetype=request.archetype,
                    age=18,
                    season_year=request.season_year,
                    seed=request.seed,
                    season_games=120,
                ),
                team_id=request.team_id,
                opponent_ids=request.opponent_ids,
            ),
        )
        return _dashboard(record)

    @router.post(
        "/{career_id}/migrate-v3",
        response_model=CareerV4Dashboard,
        status_code=status.HTTP_201_CREATED,
    )
    def migrate_endpoint(career_id: str, request: MigrateCareerV4Request) -> CareerV4Dashboard:
        legacy = legacy_repository.get(career_id)
        record = repository.create(
            career_id=career_id,
            operation_id=request.operation_id,
            expected_revision=request.expected_revision,
            action="migrate-v3",
            request_payload=request.model_dump(mode="json"),
            aggregate_factory=lambda _career_id: migrate_v3_career(
                legacy.state,
                team_id=request.team_id,
                opponent_ids=request.opponent_ids,
            ),
        )
        return _dashboard(record)

    @router.get("/{career_id}/dashboard", response_model=CareerV4Dashboard)
    def dashboard_endpoint(career_id: str) -> CareerV4Dashboard:
        return _dashboard(repository.get(career_id))

    @router.post("/{career_id}/plan-week", response_model=CareerV4Dashboard)
    def plan_week_endpoint(career_id: str, request: PlanCareerWeekRequest) -> CareerV4Dashboard:
        actions = tuple(
            PlannedAction(Weekday(item.weekday), item.action) for item in request.actions
        )
        return _dashboard(
            repository.mutate(
                career_id=career_id,
                operation_id=request.operation_id,
                action="plan-week",
                expected_revision=request.expected_revision,
                request_payload=request.model_dump(mode="json"),
                operation=lambda aggregate: submit_plan(aggregate, actions),
            )
        )

    @router.post("/{career_id}/advance-day", response_model=CareerV4Dashboard)
    def advance_day_endpoint(career_id: str, request: AdvanceCareerDayRequest) -> CareerV4Dashboard:
        return _dashboard(
            repository.mutate(
                career_id=career_id,
                operation_id=request.operation_id,
                action="advance-day",
                expected_revision=request.expected_revision,
                request_payload=request.model_dump(mode="json"),
                operation=advance_one_day,
            )
        )

    @router.post("/{career_id}/play-game", response_model=CareerV4Dashboard)
    def play_game_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(
            career_id, request, "play-game", start_interactive_game
        )

    @router.post("/{career_id}/resolve-pa", response_model=CareerV4Dashboard)
    def resolve_pa_endpoint(
        career_id: str, request: ResolveCareerPARequest
    ) -> CareerV4Dashboard:
        return _dashboard(
            repository.mutate(
                career_id=career_id,
                operation_id=request.operation_id,
                action="resolve-pa",
                expected_revision=request.expected_revision,
                request_payload=request.model_dump(mode="json"),
                operation=lambda aggregate: resolve_interactive_pa(
                    aggregate,
                    approach=BattingApproach(request.approach),
                    baserunning=BaserunningStrategy(request.baserunning),
                ),
            )
        )

    @router.post("/{career_id}/simulate-game", response_model=CareerV4Dashboard)
    def simulate_game_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(
            career_id, request, "simulate-game", simulate_interactive_game
        )

    @router.post("/{career_id}/acknowledge-game", response_model=CareerV4Dashboard)
    def acknowledge_game_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(
            career_id,
            request,
            "acknowledge-game",
            acknowledge_interactive_game,
        )

    def _mutate_simple(
        career_id: str,
        request: AdvanceCareerDayRequest,
        action: str,
        operation: Callable[[CareerAggregateV4], CareerAggregateV4],
    ) -> CareerV4Dashboard:
        return _dashboard(
            repository.mutate(
                career_id=career_id,
                operation_id=request.operation_id,
                action=action,
                expected_revision=request.expected_revision,
                request_payload=request.model_dump(mode="json"),
                operation=operation,
            )
        )

    @router.post("/{career_id}/simulate-week", response_model=CareerV4Dashboard)
    def simulate_week_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(career_id, request, "simulate-week", simulate_current_week)

    @router.post("/{career_id}/simulate-season", response_model=CareerV4Dashboard)
    def simulate_season_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(career_id, request, "simulate-season", simulate_regular_season)

    @router.post("/{career_id}/advance-phase", response_model=CareerV4Dashboard)
    def advance_phase_endpoint(
        career_id: str, request: AdvanceCareerDayRequest
    ) -> CareerV4Dashboard:
        return _mutate_simple(career_id, request, "advance-phase", advance_career_phase)

    return router
