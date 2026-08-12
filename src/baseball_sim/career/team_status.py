"""Pure Career v0.4 coach-trust, status and participation decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from baseball_sim.game.simulation import counter_uniform

TEAM_STATUS_MODEL_VERSION = "career-team-status-v0.1"


class TeamStatus(StrEnum):
    MINOR_BENCH = "minor_bench"
    MINOR_STARTER = "minor_starter"
    MAJOR_BENCH = "major_bench"
    MAJOR_STARTER = "major_starter"
    CORE_PLAYER = "core_player"
    STAR = "star"


class CompetitionLevel(StrEnum):
    MINOR = "minor"
    MAJOR = "major"


class ParticipationRole(StrEnum):
    STARTER = "starter"
    PINCH_HIT = "pinch_hit"
    PINCH_RUN = "pinch_run"
    NO_APPEARANCE = "no_appearance"


@dataclass(frozen=True, slots=True)
class TeamStanding:
    coach_trust: float = 25.0
    status: TeamStatus = TeamStatus.MINOR_BENCH
    promotion_weeks: int = 0
    demotion_weeks: int = 0

    def __post_init__(self) -> None:
        if not math.isfinite(self.coach_trust) or not 0.0 <= self.coach_trust <= 100.0:
            raise ValueError("coach trust must be finite and between 0 and 100")
        if self.promotion_weeks < 0 or self.demotion_weeks < 0:
            raise ValueError("status hysteresis counters cannot be negative")


@dataclass(frozen=True, slots=True)
class ParticipationDecision:
    level: CompetitionLevel
    role: ParticipationRole
    start_probability: float
    draw: float


_ORDER = tuple(TeamStatus)
_THRESHOLD = {
    TeamStatus.MINOR_BENCH: 0.0,
    TeamStatus.MINOR_STARTER: 30.0,
    TeamStatus.MAJOR_BENCH: 48.0,
    TeamStatus.MAJOR_STARTER: 62.0,
    TeamStatus.CORE_PLAYER: 77.0,
    TeamStatus.STAR: 90.0,
}
_START_BASE = {
    TeamStatus.MINOR_BENCH: 0.12,
    TeamStatus.MINOR_STARTER: 0.68,
    TeamStatus.MAJOR_BENCH: 0.25,
    TeamStatus.MAJOR_STARTER: 0.78,
    TeamStatus.CORE_PLAYER: 0.90,
    TeamStatus.STAR: 0.94,
}
_PINCH_HIT = {
    TeamStatus.MINOR_BENCH: 0.15,
    TeamStatus.MINOR_STARTER: 0.20,
    TeamStatus.MAJOR_BENCH: 0.35,
    TeamStatus.MAJOR_STARTER: 0.25,
    TeamStatus.CORE_PLAYER: 0.18,
    TeamStatus.STAR: 0.10,
}


def update_coach_trust(
    standing: TeamStanding,
    *,
    performance_z: float,
    discipline: float,
    availability: float,
) -> TeamStanding:
    values = (performance_z, discipline, availability)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("coach-trust inputs must be finite")
    performance = min(2.0, max(-2.0, performance_z))
    discipline = min(1.0, max(-1.0, discipline))
    availability = min(1.0, max(-1.0, availability))
    delta = 0.9 * performance + 0.8 * discipline + 0.5 * availability
    delta += 0.04 * (50.0 - standing.coach_trust)
    delta = min(4.0, max(-4.0, delta))
    return replace(standing, coach_trust=min(100.0, max(0.0, standing.coach_trust + delta)))


def readiness_score(
    standing: TeamStanding,
    *,
    ability_percentile: float,
    performance_percentile: float,
    position_need: float,
    fatigue: float,
) -> float:
    values = (ability_percentile, performance_percentile, position_need, fatigue)
    if any(not math.isfinite(value) or not 0.0 <= value <= 100.0 for value in values):
        raise ValueError("readiness inputs must be finite percent scales")
    score = 0.40 * standing.coach_trust
    score += 0.25 * ability_percentile + 0.20 * performance_percentile
    score += 0.15 * position_need - 0.10 * max(fatigue - 40.0, 0.0)
    return min(100.0, max(0.0, score))


def evaluate_status(standing: TeamStanding, readiness: float) -> TeamStanding:
    """Promote after two strong weeks; demote only after three weak weeks."""
    if not math.isfinite(readiness) or not 0.0 <= readiness <= 100.0:
        raise ValueError("readiness must be finite and between 0 and 100")
    index = _ORDER.index(standing.status)
    promote = index < len(_ORDER) - 1 and readiness >= _THRESHOLD[_ORDER[index + 1]] + 3.0
    demote = index > 0 and readiness <= _THRESHOLD[standing.status] - 5.0
    promotion_weeks = standing.promotion_weeks + 1 if promote else 0
    demotion_weeks = standing.demotion_weeks + 1 if demote else 0
    status = standing.status
    if promotion_weeks >= 2:
        status = _ORDER[index + 1]
        promotion_weeks = demotion_weeks = 0
    elif demotion_weeks >= 3:
        status = _ORDER[index - 1]
        promotion_weeks = demotion_weeks = 0
    return TeamStanding(standing.coach_trust, status, promotion_weeks, demotion_weeks)


def start_probability(
    standing: TeamStanding,
    *,
    fatigue: float,
    form_latent: float,
    depth_penalty: float,
    injured: bool = False,
) -> float:
    values = (fatigue, form_latent, depth_penalty)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("participation inputs must be finite")
    if not 0.0 <= fatigue <= 100.0 or not -2.0 <= form_latent <= 2.0:
        raise ValueError("fatigue or form is outside its supported range")
    if not 0.0 <= depth_penalty <= 0.40:
        raise ValueError("depth penalty must be between 0 and 0.40")
    if injured:
        return 0.0
    probability = _START_BASE[standing.status] + 0.002 * (standing.coach_trust - 50.0)
    probability += 0.025 * form_latent - 0.006 * max(fatigue - 55.0, 0.0)
    return min(0.97, max(0.05, probability - depth_penalty))


def decide_participation(
    standing: TeamStanding,
    *,
    fatigue: float,
    form_latent: float,
    depth_penalty: float,
    speed_rating: float,
    injured: bool,
    seed: int,
    game_number: int,
) -> ParticipationDecision:
    if not math.isfinite(speed_rating) or not 30.0 <= speed_rating <= 110.0:
        raise ValueError("speed rating must be between 30 and 110")
    if game_number < 1:
        raise ValueError("game number must be positive")
    level = (
        CompetitionLevel.MINOR
        if standing.status in {TeamStatus.MINOR_BENCH, TeamStatus.MINOR_STARTER}
        else CompetitionLevel.MAJOR
    )
    probability = start_probability(
        standing,
        fatigue=fatigue,
        form_latent=form_latent,
        depth_penalty=depth_penalty,
        injured=injured,
    )
    draw = counter_uniform(seed, game_number, "career-participation", TEAM_STATUS_MODEL_VERSION)
    if injured:
        role = ParticipationRole.NO_APPEARANCE
    elif draw < probability:
        role = ParticipationRole.STARTER
    else:
        remainder = (draw - probability) / (1.0 - probability)
        pinch_run = min(0.25, 0.05 + 0.003 * max(speed_rating - 65.0, 0.0))
        if remainder < pinch_run:
            role = ParticipationRole.PINCH_RUN
        elif remainder < pinch_run + _PINCH_HIT[standing.status]:
            role = ParticipationRole.PINCH_HIT
        else:
            role = ParticipationRole.NO_APPEARANCE
    return ParticipationDecision(level, role, probability, draw)
