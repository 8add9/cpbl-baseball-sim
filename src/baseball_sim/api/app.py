"""FastAPI application factory for the numerical baseball game."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from baseball_sim.career import (
    CareerState,
    create_career,
    play_game,
    simulate_games,
    simulate_season,
    simulate_to_next_event,
    simulate_week,
    spend_development_points,
)
from baseball_sim.career import (
    next_pa as play_next_career_pa,
)

from .career_repository import (
    CareerCorruptError,
    CareerNotFoundError,
    CareerOperationConflictError,
    CareerRevisionConflictError,
    CareerValidationError,
    SqliteCareerRepository,
)
from .career_schemas import (
    CareerListResponse,
    CareerViewResponse,
    CreateCareerRequest,
    NextCareerPARequest,
    SimulateGameRequest,
    SimulateMonthRequest,
    SimulateSeasonRequest,
    SimulateToNextEventRequest,
    SimulateWeekRequest,
    TrainCareerRequest,
)
from .career_views import career_view
from .repository import (
    GameFinishedError,
    GameNotFoundError,
    GameSession,
    InMemoryGameRepository,
    SimulationLimitError,
)
from .schemas import (
    BasesResponse,
    BatterRatingsResponse,
    CreateGameRequest,
    ErrorResponse,
    GameEventResponse,
    GameStateResponse,
    GameViewResponse,
    PitcherRatingsResponse,
    ResetGameRequest,
)


def _view(session: GameSession) -> GameViewResponse:
    state = session.state
    batter = session.batter_cards[state.batter]
    pitcher = session.pitcher_cards[state.pitcher]
    return GameViewResponse(
        game_id=session.game_id,
        model_version=state.simulation_model_version,
        state=GameStateResponse(
            inning=state.inning,
            half=state.half.value,
            outs=state.outs,
            bases=BasesResponse(
                first=state.bases[0], second=state.bases[1], third=state.bases[2]
            ),
            away_score=state.away_score,
            home_score=state.home_score,
            batting_team=state.batting_team.value,
            batter=state.batter,
            pitcher=state.pitcher,
            finished=state.finished,
            winner=None if state.winner is None else state.winner.value,
            seed=state.seed,
            plate_appearances=state.plate_appearances,
            away_lineup=list(state.away_lineup),
            home_lineup=list(state.home_lineup),
        ),
        batter_ratings=BatterRatingsResponse(
            contact=batter.contact, power=batter.power, eye=batter.eye
        ),
        pitcher_ratings=PitcherRatingsResponse(
            stuff=pitcher.stuff,
            control=pitcher.control,
            hr_suppression=pitcher.hr_suppression,
        ),
        events=[
            GameEventResponse.model_validate(
                {
                    "sequence": index,
                    "outcome": event.outcome,
                    "batter": event.batter,
                    "pitcher": event.pitcher,
                    "runs_scored": event.runs_scored,
                    "inning": event.inning,
                    "half": event.half,
                    "description": event.description,
                }
            )
            for index, event in enumerate(session.events, start=1)
        ],
    )


def _default_career_database() -> Path:
    configured = os.getenv("BASEBALL_SIM_DATA_DIR")
    if configured:
        root = Path(configured)
    elif os.name == "nt" and os.getenv("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "cpbl-baseball-sim"
    else:
        root = Path.home() / ".local" / "share" / "cpbl-baseball-sim"
    return root / "careers.sqlite3"


def create_app(
    repository: InMemoryGameRepository | None = None,
    career_repository: SqliteCareerRepository | None = None,
) -> FastAPI:
    sessions = repository or InMemoryGameRepository()
    careers = career_repository or SqliteCareerRepository(_default_career_database())
    application = FastAPI(title="CPBL Baseball Simulator API", version="0.1.0")
    application.state.game_repository = sessions
    application.state.career_repository = careers

    @application.exception_handler(GameNotFoundError)
    async def game_not_found(_request: Request, _error: GameNotFoundError) -> JSONResponse:
        body = ErrorResponse(code="game_not_found", message="Game session was not found.")
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=body.model_dump())

    @application.exception_handler(GameFinishedError)
    async def game_finished(_request: Request, _error: GameFinishedError) -> JSONResponse:
        body = ErrorResponse(code="game_finished", message="The game is already finished.")
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(SimulationLimitError)
    async def simulation_limit(_request: Request, error: SimulationLimitError) -> JSONResponse:
        body = ErrorResponse(code="simulation_limit", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(code="invalid_request", message="Request validation failed.")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(),
        )

    @application.exception_handler(CareerNotFoundError)
    async def career_not_found(_request: Request, _error: CareerNotFoundError) -> JSONResponse:
        body = ErrorResponse(code="career_not_found", message="Career save was not found.")
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=body.model_dump())

    @application.exception_handler(CareerRevisionConflictError)
    async def career_revision_conflict(
        _request: Request, error: CareerRevisionConflictError
    ) -> JSONResponse:
        body = ErrorResponse(code="revision_conflict", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(CareerOperationConflictError)
    async def career_operation_conflict(
        _request: Request, error: CareerOperationConflictError
    ) -> JSONResponse:
        body = ErrorResponse(code="operation_conflict", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(CareerCorruptError)
    async def career_corrupt(_request: Request, error: CareerCorruptError) -> JSONResponse:
        body = ErrorResponse(code="career_corrupt", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(CareerValidationError)
    async def career_invalid(_request: Request, error: CareerValidationError) -> JSONResponse:
        body = ErrorResponse(code="career_invalid", message=str(error))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(),
        )

    @application.post(
        "/api/games",
        response_model=GameViewResponse,
        status_code=status.HTTP_201_CREATED,
        responses={422: {"model": ErrorResponse}},
    )
    def create_game(request: CreateGameRequest) -> GameViewResponse:
        return _view(sessions.create(request.seed))

    @application.get(
        "/api/games/{game_id}",
        response_model=GameViewResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_game(game_id: str) -> GameViewResponse:
        return _view(sessions.get(game_id))

    @application.post(
        "/api/games/{game_id}/next-pa",
        response_model=GameViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def next_pa(game_id: str) -> GameViewResponse:
        return _view(sessions.next_pa(game_id))

    @application.post(
        "/api/games/{game_id}/simulate-half",
        response_model=GameViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_half(game_id: str) -> GameViewResponse:
        return _view(sessions.simulate_half(game_id))

    @application.post(
        "/api/games/{game_id}/simulate-full",
        response_model=GameViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_full(game_id: str) -> GameViewResponse:
        return _view(sessions.simulate_full(game_id))

    @application.post(
        "/api/games/{game_id}/reset",
        response_model=GameViewResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def reset_game(game_id: str, request: ResetGameRequest | None = None) -> GameViewResponse:
        return _view(sessions.reset(game_id, None if request is None else request.seed))

    @application.post(
        "/api/careers",
        response_model=CareerViewResponse,
        status_code=status.HTTP_201_CREATED,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_career_endpoint(request: CreateCareerRequest) -> CareerViewResponse:
        payload = request.model_dump(mode="json")
        record = careers.create(
            operation_id=request.operation_id,
            expected_revision=request.expected_revision,
            request_payload=payload,
            state_factory=lambda career_id: create_career(
                player_id=career_id,
                name=request.name,
                position=request.position,
                bats=request.bats,
                throws=request.throws,
                archetype=request.archetype,
                age=18,
                season_year=request.season_year,
                seed=request.seed,
                season_games=request.season_games,
            ),
        )
        return career_view(record)

    @application.get("/api/careers", response_model=CareerListResponse)
    def list_careers() -> CareerListResponse:
        return CareerListResponse(careers=[career_view(record) for record in careers.list()])

    @application.get(
        "/api/careers/{career_id}",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def get_career(career_id: str) -> CareerViewResponse:
        return career_view(careers.get(career_id))

    @application.post(
        "/api/careers/{career_id}/train",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def train_career(career_id: str, request: TrainCareerRequest) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="train",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: spend_development_points(
                state, request.skill, request.purchases
            ),
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/next-pa",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def next_career_pa(
        career_id: str, request: NextCareerPARequest
    ) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="next-pa",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: play_next_career_pa(
                state, plate_appearances=request.plate_appearances
            ),
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/simulate-game",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_career_game(
        career_id: str, request: SimulateGameRequest
    ) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="simulate-game",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: play_game(
                state, plate_appearances=request.plate_appearances
            ),
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/simulate-month",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_career_month(
        career_id: str, request: SimulateMonthRequest
    ) -> CareerViewResponse:
        def operation(state: CareerState) -> CareerState:
            remaining = state.origin.season_games - state.games_played
            games = min(request.games, 20, remaining)
            if games <= 0:
                raise ValueError("the current season schedule is complete")
            return simulate_games(
                state, games, plate_appearances=request.plate_appearances
            )

        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="simulate-month",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=operation,
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/simulate-week",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_career_week(
        career_id: str, request: SimulateWeekRequest
    ) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="simulate-week",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: simulate_week(
                state,
                request.games,
                plate_appearances=request.plate_appearances,
            ),
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/simulate-to-next-event",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_career_to_next_event(
        career_id: str, request: SimulateToNextEventRequest
    ) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="simulate-to-next-event",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: simulate_to_next_event(
                state, plate_appearances=request.plate_appearances
            ),
        )
        return career_view(record)

    @application.post(
        "/api/careers/{career_id}/simulate-season",
        response_model=CareerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def simulate_career_season(
        career_id: str, request: SimulateSeasonRequest
    ) -> CareerViewResponse:
        record = careers.mutate(
            career_id=career_id,
            operation_id=request.operation_id,
            action="simulate-season",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state: simulate_season(
                state, plate_appearances=request.plate_appearances
            ),
        )
        return career_view(record)

    return application


app = create_app()
