"""HTTP contracts for the minimal Career v4 weekly vertical slice."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from baseball_sim.career.models import BatterArchetype, Handedness
from baseball_sim.career.weekly import WeeklyAction


class CareerV4Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class CreateCareerV4Request(CareerV4Mutation):
    name: str = Field(min_length=1, max_length=60)
    position: str = Field(min_length=1, max_length=20)
    bats: Handedness
    throws: Literal[Handedness.LEFT, Handedness.RIGHT]
    archetype: BatterArchetype
    season_year: int = Field(ge=1990, le=2200)
    seed: int
    team_id: str = Field(min_length=1, max_length=32)
    opponent_ids: tuple[str, str, str, str, str]


class MigrateCareerV4Request(CareerV4Mutation):
    team_id: str = Field(min_length=1, max_length=32)
    opponent_ids: tuple[str, str, str, str, str]


class PlannedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=1, le=7)
    action: WeeklyAction


class PlanCareerWeekRequest(CareerV4Mutation):
    actions: tuple[PlannedActionRequest, ...] = Field(max_length=3)


class AdvanceCareerDayRequest(CareerV4Mutation):
    pass


class ResolveCareerPARequest(CareerV4Mutation):
    approach: Literal[
        "normal", "aggressive", "patient", "power_swing", "contact", "situational"
    ]
    baserunning: Literal["conservative", "balanced", "aggressive"]


class CareerV4CalendarDay(BaseModel):
    weekday: int
    is_game_day: bool
    opponent_id: str | None
    is_home: bool | None
    planned_action: str | None


class CareerV4Skill(BaseModel):
    score: float
    rating_raw: float
    rating_display: int
    xp: float


class CareerV4Stats(BaseModel):
    games: int
    pa: int
    hits: int
    home_runs: int
    walks: int
    strikeouts: int
    runs: int
    rbi: int
    stolen_bases: int
    caught_stealing: int
    avg: float
    obp: float
    slg: float
    ops: float


class CareerV4ActiveGame(BaseModel):
    inning: int
    half: str
    outs: int
    bases: tuple[bool, bool, bool]
    away_score: int
    home_score: int
    player_on_base: int | None
    last_outcome: str | None
    season_game_number: int


class CareerV4Dashboard(BaseModel):
    model_config = ConfigDict(frozen=True)
    career_id: str
    revision: int
    autosaved_at: str
    persistence_version: str
    schema_version: int
    model_version: str
    migrated_from_schema: int | None
    name: str
    position: str
    bats: str
    throws: str
    archetype: str
    age: int
    season_year: int
    games_played: int
    week: int
    weekday: int
    phase: str
    current_plan: list[PlannedActionRequest] | None
    action_points_remaining: int
    fatigue: float
    form: float
    injured: bool
    coach_trust: float
    team_status: str
    skills: dict[str, CareerV4Skill]
    season_stats: CareerV4Stats
    career_stats: CareerV4Stats
    completed_seasons: int
    calendar_days: list[CareerV4CalendarDay]
    available_actions: list[str]
    season_award: str | None
    contract_summary: str | None
    active_game: CareerV4ActiveGame | None
