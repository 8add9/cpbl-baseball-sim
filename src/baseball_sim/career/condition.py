"""Pure, deterministic Career v0.4 condition rules.

Permanent skill scores never change here.  Fatigue and form produce temporary
effective scores, while injury draws use the shared counter-based sampler.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from baseball_sim.game.simulation import counter_uniform

CONDITION_MODEL_VERSION = "career-condition-v0.1"


class CareerActivity(StrEnum):
    NONE = "none"
    STARTER_GAME = "starter_game"
    BENCH_APPEARANCE = "bench_appearance"
    FOCUSED_TRAINING = "focused_training"
    SPEED_TRAINING = "speed_training"
    VIDEO_STUDY = "video_study"
    EXTRA_BATTING_PRACTICE = "extra_batting_practice"
    RECOVERY = "recovery"


class InjurySeverity(StrEnum):
    DAY_TO_DAY = "day_to_day"
    ONE_WEEK = "one_week"
    MULTI_WEEK = "multi_week"


@dataclass(frozen=True, slots=True)
class Injury:
    severity: InjurySeverity
    days_remaining: int

    def __post_init__(self) -> None:
        maximum = {
            InjurySeverity.DAY_TO_DAY: 3,
            InjurySeverity.ONE_WEEK: 7,
            InjurySeverity.MULTI_WEEK: 28,
        }[self.severity]
        if not 1 <= self.days_remaining <= maximum:
            raise ValueError("injury duration does not match severity")


@dataclass(frozen=True, slots=True)
class CareerCondition:
    fatigue: float = 15.0
    form_latent: float = 0.0
    injury: Injury | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.fatigue) or not 0.0 <= self.fatigue <= 100.0:
            raise ValueError("fatigue must be finite and between 0 and 100")
        if not math.isfinite(self.form_latent) or not -2.0 <= self.form_latent <= 2.0:
            raise ValueError("form must be finite and between -2 and 2")

    @property
    def available(self) -> bool:
        return self.injury is None


_FATIGUE_CHANGE = {
    CareerActivity.NONE: 0.0,
    CareerActivity.STARTER_GAME: 7.0,
    CareerActivity.BENCH_APPEARANCE: 3.0,
    CareerActivity.FOCUSED_TRAINING: 8.0,
    CareerActivity.SPEED_TRAINING: 5.0,
    CareerActivity.VIDEO_STUDY: 2.0,
    CareerActivity.EXTRA_BATTING_PRACTICE: 6.0,
    CareerActivity.RECOVERY: -18.0,
}


def injury_probability(fatigue: float, *, intense_training: bool = False) -> float:
    if not math.isfinite(fatigue) or not 0.0 <= fatigue <= 100.0:
        raise ValueError("fatigue must be finite and between 0 and 100")
    probability = 0.0004 + 0.0000045 * max(fatigue - 40.0, 0.0) ** 2
    return probability * (1.35 if intense_training else 1.0)


def apply_activity(condition: CareerCondition, activity: CareerActivity) -> CareerCondition:
    allowed_while_injured = {CareerActivity.NONE, CareerActivity.RECOVERY}
    if condition.injury is not None and activity not in allowed_while_injured:
        raise ValueError("an injured player cannot train or appear in a game")
    fatigue = min(100.0, max(0.0, condition.fatigue + _FATIGUE_CHANGE[activity]))
    return replace(condition, fatigue=fatigue)


def advance_day(condition: CareerCondition) -> CareerCondition:
    """Apply natural recovery and advance an existing injury by one day."""
    injury = condition.injury
    if injury is not None:
        injury = (
            None
            if injury.days_remaining == 1
            else replace(injury, days_remaining=injury.days_remaining - 1)
        )
    return CareerCondition(max(0.0, condition.fatigue - 2.0), condition.form_latent, injury)


def _draw(seed: int, counter: int, channel: str) -> float:
    if counter < 0:
        raise ValueError("counter must be non-negative")
    return counter_uniform(seed, counter, channel, CONDITION_MODEL_VERSION)


def roll_injury(
    condition: CareerCondition,
    *,
    seed: int,
    counter: int,
    intense_training: bool = False,
) -> CareerCondition:
    """Roll at most one injury for an available player; existing injuries are stable."""
    if condition.injury is not None:
        return condition
    probability = injury_probability(condition.fatigue, intense_training=intense_training)
    if _draw(seed, counter, "career-injury-occurs") >= probability:
        return condition
    severity_draw = _draw(seed, counter, "career-injury-severity")
    if severity_draw < 0.70:
        duration = 1 + int(3 * _draw(seed, counter, "career-injury-duration"))
        injury = Injury(InjurySeverity.DAY_TO_DAY, min(duration, 3))
    elif severity_draw < 0.95:
        injury = Injury(InjurySeverity.ONE_WEEK, 7)
    else:
        duration = 14 + int(15 * _draw(seed, counter, "career-injury-duration"))
        injury = Injury(InjurySeverity.MULTI_WEEK, min(duration, 28))
    return replace(condition, injury=injury)


def _normal_draw(seed: int, counter: int) -> float:
    first = max(_draw(seed, counter, "career-form-normal-u1"), 2**-64)
    second = _draw(seed, counter, "career-form-normal-u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def update_form(
    condition: CareerCondition,
    performance_z: float,
    *,
    seed: int,
    week: int,
) -> CareerCondition:
    if not math.isfinite(performance_z):
        raise ValueError("performance z-score must be finite")
    if week < 0:
        raise ValueError("week must be non-negative")
    performance = min(2.0, max(-2.0, performance_z))
    latent = 0.72 * condition.form_latent + 0.12 * performance
    latent += 0.22 * _normal_draw(seed, week)
    return replace(condition, form_latent=min(2.0, max(-2.0, latent)))


def training_efficiency(condition: CareerCondition) -> float:
    if condition.injury is not None:
        return 0.0
    if condition.fatigue <= 30.0:
        return 1.0
    return max(0.35, 1.0 - 0.0125 * (condition.fatigue - 30.0))

