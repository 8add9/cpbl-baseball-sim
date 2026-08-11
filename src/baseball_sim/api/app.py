"""FastAPI application factory for the numerical baseball game."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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


def create_app(repository: InMemoryGameRepository | None = None) -> FastAPI:
    sessions = repository or InMemoryGameRepository()
    application = FastAPI(title="CPBL Baseball Simulator API", version="0.1.0")
    application.state.game_repository = sessions

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

    return application


app = create_app()
