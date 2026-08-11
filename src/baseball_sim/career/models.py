"""Immutable value objects for a batter-only career."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from baseball_sim.game.state import GameState
from baseball_sim.ratings.mapping import rating_display, score_to_rating
from baseball_sim.simulation.outcomes import Outcome

CAREER_SCHEMA_VERSION = 3
CAREER_MODEL_VERSION = "batter-career-v0.3"
DEFAULT_SEASON_GAMES = 120
MAX_COMPLETED_SEASONS = 20


class BatterArchetype(StrEnum):
    CONTACT = "contact"
    POWER = "power"
    PATIENT = "patient"
    BALANCED = "balanced"


class BatterSkill(StrEnum):
    CONTACT = "contact"
    POWER = "power"
    EYE = "eye"
    SPEED_PROXY = "speed_proxy"


class Handedness(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class BatterSkillScores:
    contact: float
    power: float
    eye: float
    speed_proxy: float

    def __post_init__(self) -> None:
        for value in (self.contact, self.power, self.eye, self.speed_proxy):
            if not math.isfinite(value) or not -10.0 <= value <= 10.0:
                raise ValueError("career scores must be finite and within [-10, 10]")

    def get(self, skill: BatterSkill) -> float:
        return {
            BatterSkill.CONTACT: self.contact,
            BatterSkill.POWER: self.power,
            BatterSkill.EYE: self.eye,
            BatterSkill.SPEED_PROXY: self.speed_proxy,
        }[skill]

    def with_value(self, skill: BatterSkill, value: float) -> BatterSkillScores:
        values = {
            "contact": self.contact,
            "power": self.power,
            "eye": self.eye,
            "speed_proxy": self.speed_proxy,
        }
        values[skill.value] = value
        return BatterSkillScores(**values)

    @property
    def total(self) -> float:
        return self.contact + self.power + self.eye + self.speed_proxy

    def to_ratings(self) -> BatterSkillRatings:
        return BatterSkillRatings(
            score_to_rating(self.contact),
            score_to_rating(self.power),
            score_to_rating(self.eye),
            score_to_rating(self.speed_proxy),
        )


@dataclass(frozen=True, slots=True)
class BatterSkillRatings:
    contact: float
    power: float
    eye: float
    speed_proxy: float

    def __post_init__(self) -> None:
        for value in (self.contact, self.power, self.eye, self.speed_proxy):
            if not math.isfinite(value) or not 30.0 < value < 110.0:
                raise ValueError("derived ratings must be finite and strictly between 30 and 110")

    @property
    def display(self) -> tuple[int, int, int, int]:
        return (
            rating_display(self.contact),
            rating_display(self.power),
            rating_display(self.eye),
            rating_display(self.speed_proxy),
        )


ARCHETYPE_SCORES: dict[BatterArchetype, BatterSkillScores] = {
    BatterArchetype.CONTACT: BatterSkillScores(0.2, -1.2, -0.8, -0.6),
    BatterArchetype.POWER: BatterSkillScores(-0.9, 0.4, -1.0, -0.9),
    BatterArchetype.PATIENT: BatterSkillScores(-0.8, -1.1, 0.3, -0.8),
    BatterArchetype.BALANCED: BatterSkillScores(-0.6, -0.6, -0.6, -0.6),
}


def archetype_potential(archetype: BatterArchetype) -> BatterSkillScores:
    if archetype is BatterArchetype.BALANCED:
        return BatterSkillScores(5.5, 5.5, 5.5, 5.5)
    primary = {
        BatterArchetype.CONTACT: BatterSkill.CONTACT,
        BatterArchetype.POWER: BatterSkill.POWER,
        BatterArchetype.PATIENT: BatterSkill.EYE,
    }[archetype]
    return BatterSkillScores(
        **{skill.value: 6.5 if skill is primary else 5.0 for skill in BatterSkill}
    )


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    player_id: str
    name: str
    position: str
    bats: Handedness
    throws: Handedness
    archetype: BatterArchetype

    def __post_init__(self) -> None:
        if not self.player_id.strip() or len(self.player_id) > 64:
            raise ValueError("player_id must contain 1 to 64 characters")
        if not self.name.strip() or len(self.name) > 60:
            raise ValueError("name must contain 1 to 60 characters")
        if not self.position.strip() or len(self.position) > 20:
            raise ValueError("position must contain 1 to 20 characters")
        if self.throws is Handedness.SWITCH:
            raise ValueError("throws cannot be switch")


@dataclass(frozen=True, slots=True)
class BattingStats:
    games: int = 0
    pa: int = 0
    ab: int = 0
    hits: int = 0
    singles: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    walks: int = 0
    hbp: int = 0
    strikeouts: int = 0
    total_bases: int = 0

    def __post_init__(self) -> None:
        values = (
            self.games,
            self.pa,
            self.ab,
            self.hits,
            self.singles,
            self.doubles,
            self.triples,
            self.home_runs,
            self.walks,
            self.hbp,
            self.strikeouts,
            self.total_bases,
        )
        if any(value < 0 for value in values):
            raise ValueError("batting statistics cannot be negative")
        if self.hits != self.singles + self.doubles + self.triples + self.home_runs:
            raise ValueError("hits must equal the sum of hit types")
        expected_tb = self.singles + 2 * self.doubles + 3 * self.triples + 4 * self.home_runs
        if self.total_bases != expected_tb:
            raise ValueError("total bases do not match hit types")
        if self.pa != self.ab + self.walks + self.hbp:
            raise ValueError("PA must equal AB + BB + HBP in the v0.1 outcome model")
        if self.hits > self.ab or self.strikeouts > self.ab:
            raise ValueError("hits and strikeouts cannot exceed at-bats")

    @property
    def avg(self) -> float:
        return self.hits / self.ab if self.ab else 0.0

    @property
    def obp(self) -> float:
        return (self.hits + self.walks + self.hbp) / self.pa if self.pa else 0.0

    @property
    def slg(self) -> float:
        return self.total_bases / self.ab if self.ab else 0.0

    @property
    def ops(self) -> float:
        return self.obp + self.slg

    def __add__(self, other: BattingStats) -> BattingStats:
        return BattingStats(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in self.__dataclass_fields__
            }
        )

    @classmethod
    def from_outcomes(cls, outcomes: tuple[Outcome, ...]) -> BattingStats:
        counts = {outcome: outcomes.count(outcome) for outcome in Outcome}
        hits = sum(
            counts[outcome]
            for outcome in (Outcome.SINGLE, Outcome.DOUBLE, Outcome.TRIPLE, Outcome.HR)
        )
        walks = counts[Outcome.BB]
        hbp = counts[Outcome.HBP]
        ab = len(outcomes) - walks - hbp
        return cls(
            games=1,
            pa=len(outcomes),
            ab=ab,
            hits=hits,
            singles=counts[Outcome.SINGLE],
            doubles=counts[Outcome.DOUBLE],
            triples=counts[Outcome.TRIPLE],
            home_runs=counts[Outcome.HR],
            walks=walks,
            hbp=hbp,
            strikeouts=counts[Outcome.SO],
            total_bases=(
                counts[Outcome.SINGLE]
                + 2 * counts[Outcome.DOUBLE]
                + 3 * counts[Outcome.TRIPLE]
                + 4 * counts[Outcome.HR]
            ),
        )


@dataclass(frozen=True, slots=True)
class CareerOrigin:
    profile: PlayerProfile
    starting_age: int
    starting_season_year: int
    starting_scores: BatterSkillScores
    potential_scores: BatterSkillScores
    seed: int
    season_games: int

    def __post_init__(self) -> None:
        if self.starting_age != 18:
            raise ValueError("v0.1 careers must debut at age 18")
        if not 1990 <= self.starting_season_year <= 2200:
            raise ValueError("starting season year is invalid")
        if not 1 <= self.season_games <= 200:
            raise ValueError("season_games must be between 1 and 200")


@dataclass(frozen=True, slots=True)
class SeasonRecord:
    season_year: int
    age: int
    scores_at_end: BatterSkillScores
    stats: BattingStats


@dataclass(frozen=True, slots=True)
class ActiveCareerGame:
    season_year: int
    game_number: int
    game_state: GameState
    career_outcomes: tuple[Outcome, ...]

    def __post_init__(self) -> None:
        if len(self.career_outcomes) > self.game_state.plate_appearances:
            raise ValueError("career outcomes exceed game plate appearances")


@dataclass(frozen=True, slots=True)
class PlateAppearancePlayedEvent:
    season_year: int
    game_number: int
    pa_index: int
    outcome: Outcome
    batter: str
    pitcher: str
    career_plate_appearance: bool
    development_points_earned: int
    development_points_expired: int
    kind: str = "plate_appearance_played"


@dataclass(frozen=True, slots=True)
class GamePlayedEvent:
    season_year: int
    game_number: int
    plate_appearances: int
    outcomes: tuple[Outcome, ...]
    xp_earned: int
    development_points_earned: int
    kind: str = "game_played"


@dataclass(frozen=True, slots=True)
class RatingImprovedEvent:
    skill: BatterSkill
    purchases: int
    points_spent: int
    score_before: float
    score_after: float
    kind: str = "rating_improved"


@dataclass(frozen=True, slots=True)
class SeasonAdvancedEvent:
    previous_year: int
    next_year: int
    new_age: int
    kind: str = "season_advanced"


@dataclass(frozen=True, slots=True)
class CareerRetiredEvent:
    season_year: int
    age: int
    kind: str = "career_retired"


CareerEvent: TypeAlias = (
    PlateAppearancePlayedEvent
    | GamePlayedEvent
    | RatingImprovedEvent
    | SeasonAdvancedEvent
    | CareerRetiredEvent
)


@dataclass(frozen=True, slots=True)
class CareerState:
    origin: CareerOrigin
    age: int
    season_year: int
    games_played: int
    experience: int
    development_points: int
    expired_development_points: int
    scores: BatterSkillScores
    season_purchases: int
    season_skill_purchases: tuple[int, int, int, int]
    active_game: ActiveCareerGame | None
    season_stats: BattingStats
    career_stats: BattingStats
    completed_seasons: tuple[SeasonRecord, ...]
    events: tuple[CareerEvent, ...]
    schema_version: int = CAREER_SCHEMA_VERSION
    model_version: str = CAREER_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAREER_SCHEMA_VERSION:
            raise ValueError("unsupported in-memory career schema version")
        if self.model_version != CAREER_MODEL_VERSION:
            raise ValueError("unsupported career model version")
        if not 16 <= self.age <= 70:
            raise ValueError("career age must be between 16 and 70")
        if self.season_year < self.origin.starting_season_year:
            raise ValueError("season cannot precede the career origin")
        if not 0 <= self.games_played <= self.origin.season_games:
            raise ValueError("games_played is outside the season schedule")
        if (
            self.experience < 0
            or self.development_points < 0
            or self.expired_development_points < 0
        ):
            raise ValueError("experience and development points cannot be negative")
        if self.development_points > 24:
            raise ValueError("development point bank cannot exceed 24")
        if not 0 <= self.season_purchases <= 12:
            raise ValueError("season purchases must be between 0 and 12")
        if len(self.season_skill_purchases) != 4 or any(
            not 0 <= value <= 4 for value in self.season_skill_purchases
        ):
            raise ValueError("each ability may be purchased at most four times per season")
        if sum(self.season_skill_purchases) != self.season_purchases:
            raise ValueError("season purchase counters do not agree")
        if self.season_stats.games != self.games_played:
            raise ValueError("season games must equal games_played")
        if self.career_stats.games < self.season_stats.games:
            raise ValueError("career stats cannot be smaller than season stats")
        years = [record.season_year for record in self.completed_seasons]
        if years != sorted(set(years)):
            raise ValueError("completed season years must be unique and ordered")
        if len(self.completed_seasons) > MAX_COMPLETED_SEASONS:
            raise ValueError("a career cannot exceed twenty completed seasons")
        if self.active_game is not None:
            if self.active_game.season_year != self.season_year:
                raise ValueError("active game season does not match career season")
            if self.active_game.game_number != self.games_played + 1:
                raise ValueError("active game number does not follow completed games")
            if self.games_played >= self.origin.season_games:
                raise ValueError("a completed schedule cannot have an active game")
            if self.origin.profile.player_id not in self.active_game.game_state.away_lineup:
                raise ValueError("active game lineup is missing the career player")

    @property
    def ratings(self) -> BatterSkillRatings:
        return self.scores.to_ratings()

    @property
    def retired(self) -> bool:
        return len(self.completed_seasons) >= MAX_COMPLETED_SEASONS


def create_career(
    *,
    player_id: str,
    name: str,
    position: str,
    bats: Handedness,
    throws: Handedness,
    archetype: BatterArchetype,
    age: int,
    season_year: int,
    seed: int,
    season_games: int = DEFAULT_SEASON_GAMES,
) -> CareerState:
    """Create a batter from a frozen archetype instead of free rating allocation."""
    profile = PlayerProfile(player_id, name, position, bats, throws, archetype)
    origin = CareerOrigin(
        profile=profile,
        starting_age=age,
        starting_season_year=season_year,
        starting_scores=ARCHETYPE_SCORES[archetype],
        potential_scores=archetype_potential(archetype),
        seed=seed,
        season_games=season_games,
    )
    return initial_state(origin)


def initial_state(origin: CareerOrigin) -> CareerState:
    return CareerState(
        origin=origin,
        age=origin.starting_age,
        season_year=origin.starting_season_year,
        games_played=0,
        experience=0,
        development_points=0,
        expired_development_points=0,
        scores=origin.starting_scores,
        season_purchases=0,
        season_skill_purchases=(0, 0, 0, 0),
        active_game=None,
        season_stats=BattingStats(),
        career_stats=BattingStats(),
        completed_seasons=(),
        events=(),
    )
