"""Pydantic contracts for persistent Career Mode operations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from baseball_sim.career.models import BatterArchetype, BatterSkill, Handedness


class MutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class CreateCareerRequest(MutationRequest):
    name: str = Field(min_length=1, max_length=60)
    position: str = Field(min_length=1, max_length=20)
    bats: Handedness
    throws: Literal[Handedness.LEFT, Handedness.RIGHT]
    archetype: BatterArchetype
    season_year: int = Field(ge=1990, le=2200)
    seed: int
    season_games: int = Field(default=120, ge=1, le=200)


class TrainCareerRequest(MutationRequest):
    skill: BatterSkill
    purchases: int = Field(default=1, ge=1, le=4)


class SimulateGameRequest(MutationRequest):
    plate_appearances: int = Field(default=4, ge=1, le=12)


class SimulateMonthRequest(MutationRequest):
    games: int = Field(default=20, ge=1, le=20)
    plate_appearances: int = Field(default=4, ge=1, le=12)


class SimulateWeekRequest(MutationRequest):
    games: int = Field(default=6, ge=1, le=6)
    plate_appearances: int = Field(default=4, ge=1, le=12)


class SimulateToNextEventRequest(MutationRequest):
    plate_appearances: int = Field(default=4, ge=1, le=12)


class NextCareerPARequest(MutationRequest):
    plate_appearances: int = Field(default=4, ge=1, le=12)


class SimulateSeasonRequest(MutationRequest):
    plate_appearances: int = Field(default=4, ge=1, le=12)


class SkillView(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float
    rating_raw: float
    rating_display: int
    potential_score: float
    next_cost: int | None
    can_train: bool


class CareerSkillsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    contact: SkillView
    power: SkillView
    eye: SkillView
    speed_proxy: SkillView


class BattingStatsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    games: int
    pa: int
    ab: int
    hits: int
    singles: int
    doubles: int
    triples: int
    home_runs: int
    walks: int
    hbp: int
    strikeouts: int
    total_bases: int
    avg: float
    obp: float
    slg: float
    ops: float


class CareerGameResultView(BaseModel):
    model_config = ConfigDict(frozen=True)

    season_year: int
    game_number: int
    plate_appearances: int
    outcomes: list[Literal["BB", "HBP", "SO", "OUT", "1B", "2B", "3B", "HR"]]
    hits: int
    home_runs: int
    walks: int
    xp_earned: int
    development_points_earned: int


class ActiveCareerGameView(BaseModel):
    model_config = ConfigDict(frozen=True)

    season_year: int
    game_number: int
    inning: int
    half: Literal["top", "bottom"]
    outs: int
    bases: list[str | None]
    away_score: int
    home_score: int
    batting_team: Literal["away", "home"]
    batter: str
    pitcher: str
    away_pitcher: str
    home_pitcher: str
    seed: int
    game_plate_appearances: int
    career_plate_appearances: int
    career_outcomes: list[
        Literal["BB", "HBP", "SO", "OUT", "1B", "2B", "3B", "HR"]
    ]
    away_lineup: list[str]
    home_lineup: list[str]


class CareerViewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    career_id: str
    revision: int = Field(ge=1)
    autosaved_at: str
    persistence_version: str
    schema_version: int
    model_version: str
    name: str
    position: str
    bats: Handedness
    throws: Handedness
    archetype: BatterArchetype
    age: int
    season_year: int
    games_played: int
    season_games: int
    experience: int
    development_points: int
    expired_development_points: int
    season_purchases: int
    retired: bool
    active_game: ActiveCareerGameView | None
    skills: CareerSkillsView
    season_stats: BattingStatsView
    career_stats: BattingStatsView
    recent_results: list[CareerGameResultView]


class CareerListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    careers: list[CareerViewResponse]
