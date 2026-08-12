"""Pydantic contracts for persistent Manager leagues."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ManagerMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class CreateManagerRequest(ManagerMutationRequest):
    seed: int = 20260812


class ReplaceManagerCardRequest(ManagerMutationRequest):
    team_id: str = Field(min_length=1, max_length=64)
    outgoing_card_id: str = Field(min_length=1, max_length=256)
    incoming_card_id: str = Field(min_length=1, max_length=256)


class StandingView(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int
    team_id: str
    wins: int
    losses: int
    runs_scored: int
    runs_allowed: int
    run_differential: int
    winning_percentage: float
    games_behind: float


class ScheduledGameView(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_number: int
    round_number: int
    away_team_id: str
    home_team_id: str


class ResultView(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_number: int
    away_team_id: str
    home_team_id: str
    away_runs: int
    home_runs: int


class LineupCardView(BaseModel):
    model_config = ConfigDict(frozen=True)

    card_id: str
    player_name: str
    season_year: int
    position: str
    profile_position: str
    role: str | None
    tier: str
    cost: int
    abilities: dict[str, float]


class RosterCardView(BaseModel):
    model_config = ConfigDict(frozen=True)

    card_id: str
    player_name: str
    season_year: int
    team: str
    profile_position: str
    role: str | None
    tier: str
    cost: int
    abilities: dict[str, float]


class ManagerCandidateListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: list[RosterCardView]


class ManagerTeamView(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_id: str
    name: str
    strategy: str
    games_played: int
    roster_cost: int
    batter_count: int
    rotation_count: int
    bullpen_count: int
    next_starter_card_id: str
    lineup: list[LineupCardView]
    bench: list[RosterCardView]
    rotation: list[RosterCardView]
    bullpen: list[RosterCardView]
    tier_counts: dict[str, int]
    available_bullpen_card_ids: list[str]


class ManagerViewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    manager_id: str
    revision: int
    autosaved_at: str
    persistence_version: str
    schema_version: int
    model_version: str
    catalog_snapshot_version: str
    catalog_fingerprint: str
    seed: int
    games_completed: int
    total_games: int
    finished: bool
    next_game: ScheduledGameView | None
    standings: list[StandingView]
    teams: list[ManagerTeamView]
    recent_results: list[ResultView]


class ManagerListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    managers: list[ManagerViewResponse]
