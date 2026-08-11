"""Immutable game-state value objects."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class Team(StrEnum):
    AWAY = "away"
    HOME = "home"


class HalfInning(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class GameState:
    away_lineup: tuple[str, ...]
    home_lineup: tuple[str, ...]
    away_pitcher: str
    home_pitcher: str
    seed: int = 20260811
    rules_version: str = "station-to-station-v0.1"
    simulation_model_version: str = "pa-hierarchical-v0.1"
    rating_snapshot_version: str = "unversioned"
    inning: int = 1
    half: HalfInning = HalfInning.TOP
    outs: int = 0
    bases: tuple[str | None, str | None, str | None] = (None, None, None)
    away_score: int = 0
    home_score: int = 0
    away_lineup_index: int = 0
    home_lineup_index: int = 0
    plate_appearances: int = 0
    finished: bool = False
    winner: Team | None = None

    def __post_init__(self) -> None:
        if len(self.away_lineup) != 9 or len(self.home_lineup) != 9:
            raise ValueError("both teams require exactly nine lineup players")
        if len(set(self.away_lineup)) != len(self.away_lineup):
            raise ValueError("away lineup players must be unique")
        if len(set(self.home_lineup)) != len(self.home_lineup):
            raise ValueError("home lineup players must be unique")
        if self.inning < 1 or not 0 <= self.outs <= 2:
            raise ValueError("inning and outs are invalid")
        if self.away_score < 0 or self.home_score < 0 or self.plate_appearances < 0:
            raise ValueError("scores and plate appearances cannot be negative")
        runners = [runner for runner in self.bases if runner is not None]
        if len(runners) != len(set(runners)):
            raise ValueError("a runner cannot occupy multiple bases")
        if not 0 <= self.away_lineup_index < len(self.away_lineup):
            raise ValueError("away lineup index is invalid")
        if not 0 <= self.home_lineup_index < len(self.home_lineup):
            raise ValueError("home lineup index is invalid")
        if self.finished != (self.winner is not None):
            raise ValueError("finished games require exactly one winner")

    @property
    def batting_team(self) -> Team:
        return Team.AWAY if self.half is HalfInning.TOP else Team.HOME

    @property
    def fielding_team(self) -> Team:
        return Team.HOME if self.batting_team is Team.AWAY else Team.AWAY

    @property
    def batter(self) -> str:
        if self.batting_team is Team.AWAY:
            return self.away_lineup[self.away_lineup_index]
        return self.home_lineup[self.home_lineup_index]

    @property
    def pitcher(self) -> str:
        return self.home_pitcher if self.batting_team is Team.AWAY else self.away_pitcher

    def with_pitcher(self, team: Team, pitcher: str) -> GameState:
        if self.finished:
            raise ValueError("cannot change pitcher in a finished game")
        if team is not self.fielding_team:
            raise ValueError("only the current fielding team may change pitcher")
        if not pitcher:
            raise ValueError("pitcher id cannot be empty")
        if team is Team.AWAY:
            return replace(self, away_pitcher=pitcher)
        return replace(self, home_pitcher=pitcher)
