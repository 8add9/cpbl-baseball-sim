"""FastAPI application factory for the numerical baseball game."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
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
from baseball_sim.manager.cards import CatalogEntry
from baseball_sim.manager.game_roster import LineupEntry
from baseball_sim.manager.league_service import (
    advance_manager_season,
    create_ai_league,
    rename_user_team,
    replace_team_card,
    simulate_league_round,
    simulate_league_season,
    simulate_next_league_game,
    update_user_lineup,
    update_user_rotation_plan,
)
from baseball_sim.ratings.mapping import rating_display

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
from .game_repository import GameWriteConflictError, SqliteGameRepository
from .manager_repository import (
    ManagerCorruptError,
    ManagerNotFoundError,
    ManagerOperationConflictError,
    ManagerRevisionConflictError,
    ManagerValidationError,
    SqliteManagerRepository,
)
from .manager_schemas import (
    CreateManagerRequest,
    ManagerCandidateListResponse,
    ManagerListResponse,
    ManagerMutationRequest,
    ManagerViewResponse,
    RenameManagerTeamRequest,
    ReplaceManagerCardRequest,
    UpdateManagerLineupRequest,
    UpdateManagerRotationRequest,
)
from .manager_views import manager_view, roster_card_view
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


def _default_manager_database() -> Path:
    return _default_career_database().with_name("managers.sqlite3")


def _default_game_database() -> Path:
    return _default_career_database().with_name("games.sqlite3")


def _default_rating_artifacts() -> Path:
    configured = os.getenv("BASEBALL_SIM_RATING_ARTIFACTS")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "artifacts" / "generated" / "ratings"


def create_app(
    repository: InMemoryGameRepository | None = None,
    career_repository: SqliteCareerRepository | None = None,
    manager_repository: SqliteManagerRepository | None = None,
) -> FastAPI:
    sessions = repository or SqliteGameRepository(_default_game_database())
    careers = career_repository or SqliteCareerRepository(_default_career_database())
    application = FastAPI(title="CPBL Baseball Simulator API", version="0.1.0")
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "BASEBALL_SIM_CORS_ORIGINS",
            "https://8add9.github.io,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "ngrok-skip-browser-warning"],
    )
    application.state.game_repository = sessions
    application.state.career_repository = careers
    application.state.manager_repository = manager_repository

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": application.version, "database": "ok"}

    @application.exception_handler(GameNotFoundError)
    async def game_not_found(_request: Request, _error: GameNotFoundError) -> JSONResponse:
        body = ErrorResponse(code="game_not_found", message="Game session was not found.")
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=body.model_dump())

    @application.exception_handler(GameFinishedError)
    async def game_finished(_request: Request, _error: GameFinishedError) -> JSONResponse:
        body = ErrorResponse(code="game_finished", message="The game is already finished.")
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(GameWriteConflictError)
    async def game_write_conflict(
        _request: Request, _error: GameWriteConflictError
    ) -> JSONResponse:
        body = ErrorResponse(
            code="game_write_conflict",
            message="The game changed on the server. Reload before retrying.",
        )
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

    @application.exception_handler(ManagerNotFoundError)
    async def manager_not_found(
        _request: Request, _error: ManagerNotFoundError
    ) -> JSONResponse:
        body = ErrorResponse(code="manager_not_found", message="Manager league was not found.")
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=body.model_dump())

    @application.exception_handler(ManagerRevisionConflictError)
    async def manager_revision_conflict(
        _request: Request, error: ManagerRevisionConflictError
    ) -> JSONResponse:
        body = ErrorResponse(code="revision_conflict", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(ManagerOperationConflictError)
    async def manager_operation_conflict(
        _request: Request, error: ManagerOperationConflictError
    ) -> JSONResponse:
        body = ErrorResponse(code="operation_conflict", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(ManagerCorruptError)
    async def manager_corrupt(
        _request: Request, error: ManagerCorruptError
    ) -> JSONResponse:
        body = ErrorResponse(code="manager_corrupt", message=str(error))
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    @application.exception_handler(ManagerValidationError)
    async def manager_invalid(
        _request: Request, error: ManagerValidationError
    ) -> JSONResponse:
        body = ErrorResponse(code="manager_invalid", message=str(error))
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

    application.add_api_route(
        "/api/games/{game_id}/simulate-half-inning",
        simulate_half,
        methods=["POST"],
        response_model=GameViewResponse,
    )
    application.add_api_route(
        "/api/games/{game_id}/simulate-game",
        simulate_full,
        methods=["POST"],
        response_model=GameViewResponse,
    )

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

    def manager_backend() -> SqliteManagerRepository:
        backend = application.state.manager_repository
        if backend is None:
            backend = SqliteManagerRepository(
                _default_manager_database(), _default_rating_artifacts()
            )
            application.state.manager_repository = backend
        return cast(SqliteManagerRepository, backend)

    def player_card(entry: CatalogEntry) -> dict[str, object]:
        card = entry.card
        return {
            "player_id": card.card_id,
            "source_player_id": card.player_id,
            "name": card.player_name,
            "season_year": card.season_year,
            "team": card.team,
            "kind": card.kind.value,
            "profile_positions": list(card.profile_positions),
            "role": None if card.pitcher_role is None else card.pitcher_role.value,
            "incomplete_season": card.incomplete_season,
            "abilities": {
                name: {
                    "score": rating.score,
                    "rating_raw": rating.rating_raw,
                    "rating_display": rating_display(rating.rating_raw),
                }
                for name, rating in card.abilities.items()
            },
        }

    @application.get("/api/players")
    def list_players(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        entries = manager_backend().catalog.entries()
        return {
            "total": len(entries),
            "players": [player_card(entry) for entry in entries[offset : offset + limit]],
        }

    @application.get("/api/players/{player_id:path}", response_model=None)
    def get_player(player_id: str) -> dict[str, object] | JSONResponse:
        try:
            return player_card(manager_backend().catalog.get(player_id))
        except KeyError:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "code": "player_not_found",
                    "message": "Player card was not found.",
                },
            )

    @application.post(
        "/api/managers",
        response_model=ManagerViewResponse,
        status_code=status.HTTP_201_CREATED,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_manager_endpoint(request: CreateManagerRequest) -> ManagerViewResponse:
        backend = manager_backend()
        record = backend.create(
            operation_id=request.operation_id,
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            state_factory=lambda catalog: create_ai_league(catalog, request.seed),
        )
        return manager_view(record, backend.catalog)

    @application.get("/api/managers", response_model=ManagerListResponse)
    def list_managers() -> ManagerListResponse:
        backend = manager_backend()
        return ManagerListResponse(
            managers=[manager_view(record, backend.catalog) for record in backend.list()]
        )

    @application.get(
        "/api/managers/{manager_id}",
        response_model=ManagerViewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def get_manager(manager_id: str) -> ManagerViewResponse:
        backend = manager_backend()
        return manager_view(backend.get(manager_id), backend.catalog)

    @application.get(
        "/api/managers/{manager_id}/roster-candidates",
        response_model=ManagerCandidateListResponse,
    )
    def manager_roster_candidates(
        manager_id: str, team_id: str, outgoing_card_id: str
    ) -> ManagerCandidateListResponse:
        backend = manager_backend()
        state = backend.get(manager_id).state
        target = next(
            (team for team in state.teams if team.config.team_id == team_id), None
        )
        if target is None:
            raise ManagerValidationError(f"unknown Manager team: {team_id}")
        roster = target.config.roster
        if outgoing_card_id not in roster.all_card_ids:
            raise ManagerValidationError("outgoing card is not on the selected team")
        claimed = {
            card_id for team in state.teams for card_id in team.config.roster.all_card_ids
        }
        remaining_player_ids = {
            backend.catalog.get(card_id).card.player_id
            for card_id in roster.all_card_ids
            if card_id != outgoing_card_id
        }
        lineup_entry = next(
            (entry for entry in target.config.lineup if entry.card_id == outgoing_card_id),
            None,
        )
        if outgoing_card_id in roster.batter_card_ids:
            group = "batter"
        elif outgoing_card_id in roster.rotation_card_ids:
            group = "rotation"
        else:
            group = "bullpen"
        candidates = []
        for entry in backend.catalog.entries(competitive_only=True):
            card = entry.card
            if card.card_id in claimed or card.player_id in remaining_player_ids:
                continue
            if group == "batter" and card.kind.value != "batter":
                continue
            if group == "rotation" and (
                card.pitcher_role is None or card.pitcher_role.value != "SP"
            ):
                continue
            if group == "bullpen" and (
                card.pitcher_role is None
                or card.pitcher_role.value not in {"RP", "Swingman"}
            ):
                continue
            if lineup_entry is not None and lineup_entry.position not in card.eligible_positions:
                continue
            candidates.append(entry)
        tier_order = {"SSR": 0, "SR": 1, "R": 2, "N": 3}
        candidates.sort(
            key=lambda entry: (
                tier_order[entry.tier.value if entry.tier is not None else "N"],
                -entry.impact,
                entry.card.card_id,
            )
        )
        # Preserve up to fifteen candidates per tier so both star-cap rejection and
        # affordable legal swaps are available to the browser roster builder.
        sampled = [
            entry
            for tier in ("SSR", "SR", "R", "N")
            for entry in [item for item in candidates if item.tier and item.tier.value == tier][
                :15
            ]
        ]
        return ManagerCandidateListResponse(
            candidates=[roster_card_view(entry) for entry in sampled]
        )

    @application.post(
        "/api/managers/{manager_id}/replace-card",
        response_model=ManagerViewResponse,
    )
    def replace_manager_card_endpoint(
        manager_id: str, request: ReplaceManagerCardRequest
    ) -> ManagerViewResponse:
        backend = manager_backend()
        record = backend.mutate(
            manager_id=manager_id,
            operation_id=request.operation_id,
            action="replace-card",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state, catalog: replace_team_card(
                state,
                catalog,
                team_id=request.team_id,
                outgoing_card_id=request.outgoing_card_id,
                incoming_card_id=request.incoming_card_id,
            ),
        )
        return manager_view(record, backend.catalog)

    @application.post(
        "/api/managers/{manager_id}/rename-team",
        response_model=ManagerViewResponse,
    )
    def rename_manager_team_endpoint(
        manager_id: str, request: RenameManagerTeamRequest
    ) -> ManagerViewResponse:
        backend = manager_backend()
        record = backend.mutate(
            manager_id=manager_id,
            operation_id=request.operation_id,
            action="rename-team",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state, _catalog: rename_user_team(state, request.name),
        )
        return manager_view(record, backend.catalog)

    @application.post(
        "/api/managers/{manager_id}/lineup",
        response_model=ManagerViewResponse,
    )
    def update_manager_lineup_endpoint(
        manager_id: str, request: UpdateManagerLineupRequest
    ) -> ManagerViewResponse:
        backend = manager_backend()
        lineup = tuple(LineupEntry(item.card_id, item.position) for item in request.lineup)
        record = backend.mutate(
            manager_id=manager_id,
            operation_id=request.operation_id,
            action="update-lineup",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state, _catalog: update_user_lineup(state, lineup),
        )
        return manager_view(record, backend.catalog)

    @application.post(
        "/api/managers/{manager_id}/rotation-plan",
        response_model=ManagerViewResponse,
    )
    def update_manager_rotation_endpoint(
        manager_id: str, request: UpdateManagerRotationRequest
    ) -> ManagerViewResponse:
        backend = manager_backend()
        starters = tuple(request.starter_card_ids)
        record = backend.mutate(
            manager_id=manager_id,
            operation_id=request.operation_id,
            action="update-rotation-plan",
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=lambda state, _catalog: update_user_rotation_plan(state, starters),
        )
        return manager_view(record, backend.catalog)

    def mutate_manager(
        manager_id: str,
        request: ManagerMutationRequest,
        action: str,
    ) -> ManagerViewResponse:
        backend = manager_backend()
        operations = {
            "simulate-next-game": simulate_next_league_game,
            "simulate-round": simulate_league_round,
            "simulate-season": simulate_league_season,
            "advance-season": advance_manager_season,
        }
        record = backend.mutate(
            manager_id=manager_id,
            operation_id=request.operation_id,
            action=action,
            expected_revision=request.expected_revision,
            request_payload=request.model_dump(mode="json"),
            operation=operations[action],
        )
        return manager_view(record, backend.catalog)

    @application.post(
        "/api/managers/{manager_id}/simulate-next-game",
        response_model=ManagerViewResponse,
    )
    def simulate_manager_next_game_endpoint(
        manager_id: str, request: ManagerMutationRequest
    ) -> ManagerViewResponse:
        return mutate_manager(manager_id, request, "simulate-next-game")

    @application.post(
        "/api/managers/{manager_id}/simulate-round",
        response_model=ManagerViewResponse,
    )
    def simulate_manager_round_endpoint(
        manager_id: str, request: ManagerMutationRequest
    ) -> ManagerViewResponse:
        return mutate_manager(manager_id, request, "simulate-round")

    @application.post(
        "/api/managers/{manager_id}/simulate-season",
        response_model=ManagerViewResponse,
    )
    def simulate_manager_season_endpoint(
        manager_id: str, request: ManagerMutationRequest
    ) -> ManagerViewResponse:
        return mutate_manager(manager_id, request, "simulate-season")

    @application.post(
        "/api/managers/{manager_id}/advance-season",
        response_model=ManagerViewResponse,
    )
    def advance_manager_season_endpoint(
        manager_id: str, request: ManagerMutationRequest
    ) -> ManagerViewResponse:
        return mutate_manager(manager_id, request, "advance-season")

    return application


app = create_app()
