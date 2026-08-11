"""Public HTTP schemas for game sessions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = 20260811


class ResetGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int | None = None


class BasesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    first: str | None
    second: str | None
    third: str | None


class GameStateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    inning: int = Field(ge=1)
    half: Literal["top", "bottom"]
    outs: int = Field(ge=0, le=2)
    bases: BasesResponse
    away_score: int = Field(ge=0)
    home_score: int = Field(ge=0)
    batting_team: Literal["away", "home"]
    batter: str
    pitcher: str
    finished: bool
    winner: Literal["away", "home"] | None
    seed: int
    plate_appearances: int = Field(ge=0)
    away_lineup: list[str]
    home_lineup: list[str]


class BatterRatingsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    contact: float
    power: float
    eye: float


class PitcherRatingsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    stuff: float
    control: float
    hr_suppression: float


class GameEventResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    outcome: Literal["BB", "HBP", "SO", "OUT", "1B", "2B", "3B", "HR"]
    batter: str
    pitcher: str
    runs_scored: int = Field(ge=0)
    inning: int = Field(ge=1)
    half: Literal["top", "bottom"]
    description: str


class GameViewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_id: str
    model_version: str
    state: GameStateResponse
    batter_ratings: BatterRatingsResponse
    pitcher_ratings: PitcherRatingsResponse
    events: list[GameEventResponse]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
