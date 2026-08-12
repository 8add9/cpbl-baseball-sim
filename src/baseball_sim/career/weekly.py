"""Pure Career v0.4 weekly planning, condition and development rules.

This module is intentionally independent from HTTP and the PA engine.  It is the first
versioned reducer in the Career v4 migration and is shared by gameplay and balance runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from baseball_sim.ratings.mapping import score_to_rating

from .models import BatterArchetype, BatterSkill, BatterSkillScores

WEEKLY_MODEL_VERSION = "career-weekly-v0.4"
WEEKLY_ACTION_POINTS = 4


class WeeklyAction(StrEnum):
    CONTACT = "contact_training"
    POWER = "power_training"
    EYE = "eye_training"
    SPEED = "speed_training"
    RECOVERY = "recovery"
    VIDEO = "video_study"
    EXTRA_BP = "extra_batting_practice"


ACTION_COST = {
    WeeklyAction.CONTACT: 2,
    WeeklyAction.POWER: 2,
    WeeklyAction.EYE: 2,
    WeeklyAction.SPEED: 1,
    WeeklyAction.RECOVERY: 1,
    WeeklyAction.VIDEO: 1,
    WeeklyAction.EXTRA_BP: 1,
}


@dataclass(frozen=True, slots=True)
class PotentialTraits:
    overall: int
    contact_affinity: int
    power_affinity: int
    eye_affinity: int
    speed_affinity: int

    def __post_init__(self) -> None:
        if not 45 <= self.overall <= 95:
            raise ValueError("overall potential must be between 45 and 95")
        if any(not -10 <= value <= 10 for value in self.affinities):
            raise ValueError("potential affinity must be between -10 and 10")

    @property
    def affinities(self) -> tuple[int, int, int, int]:
        return (
            self.contact_affinity,
            self.power_affinity,
            self.eye_affinity,
            self.speed_affinity,
        )

    def affinity(self, skill: BatterSkill) -> int:
        return self.affinities[list(BatterSkill).index(skill)]


def archetype_potential_traits(archetype: BatterArchetype) -> PotentialTraits:
    affinities = {
        BatterArchetype.CONTACT: (7, -3, 0, -1),
        BatterArchetype.POWER: (-2, 7, -3, -1),
        BatterArchetype.PATIENT: (-1, -3, 7, -1),
        BatterArchetype.SPEED: (-1, -3, -1, 7),
        BatterArchetype.BALANCED: (1, 1, 1, 1),
    }[archetype]
    return PotentialTraits(70, *affinities)


@dataclass(frozen=True, slots=True)
class WeeklyDevelopment:
    week: int = 1
    action_points: int = WEEKLY_ACTION_POINTS
    contact_xp: float = 0.0
    power_xp: float = 0.0
    eye_xp: float = 0.0
    speed_xp: float = 0.0
    contact_repeats: int = 0
    power_repeats: int = 0
    eye_repeats: int = 0
    speed_repeats: int = 0

    def __post_init__(self) -> None:
        if self.week < 1 or not 0 <= self.action_points <= WEEKLY_ACTION_POINTS:
            raise ValueError("invalid week or action-point state")
        xp_values = (self.contact_xp, self.power_xp, self.eye_xp, self.speed_xp)
        if any(not math.isfinite(value) or value < 0 for value in xp_values):
            raise ValueError("skill XP must be finite and nonnegative")
        repeat_values = (
            self.contact_repeats,
            self.power_repeats,
            self.eye_repeats,
            self.speed_repeats,
        )
        if any(not isinstance(value, int) or value < 0 for value in repeat_values):
            raise ValueError("training repeat counts must be nonnegative integers")

    def xp(self, skill: BatterSkill) -> float:
        return (self.contact_xp, self.power_xp, self.eye_xp, self.speed_xp)[
            list(BatterSkill).index(skill)
        ]

    def repeats(self, skill: BatterSkill) -> int:
        return (
            self.contact_repeats,
            self.power_repeats,
            self.eye_repeats,
            self.speed_repeats,
        )[list(BatterSkill).index(skill)]


@dataclass(frozen=True, slots=True)
class TrainingResult:
    development: WeeklyDevelopment
    scores: BatterSkillScores
    action: WeeklyAction
    xp_gained: float
    rating_before: float
    rating_after: float
    breakthrough: bool
    fatigue_delta: float


def _age_efficiency(age: int) -> float:
    if age <= 21:
        return 1.25
    if age <= 25:
        return 1.10
    if age <= 29:
        return 0.85
    if age <= 33:
        return 0.55
    return 0.30


def _xp_threshold(score: float, archetype_multiplier: float) -> float:
    return math.ceil(36 * archetype_multiplier * (1 + 0.14 * max(score, 0) ** 2))


def _deterministic_unit(seed: int, week: int, action: WeeklyAction, repeat: int) -> float:
    # A stable integer mixer keeps balance runs and save/reload independent of RNG libraries.
    value = (seed ^ (week * 0x9E3779B1) ^ (repeat * 0x85EBCA77)) & 0xFFFFFFFF
    for byte in action.value.encode():
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value / 2**32


def _train_skill(
    *,
    skill: BatterSkill,
    base_xp: float,
    score: float,
    pooled_xp: float,
    repeat: int,
    potential: PotentialTraits,
    archetype: BatterArchetype,
    age: int,
    fatigue: float,
    seed: int,
    week: int,
    action: WeeklyAction,
) -> tuple[float, float, float, bool]:
    repeat_factor = (1.0, 0.70, 0.45, 0.30)[min(repeat, 3)]
    soft_center = 68 + 0.27 * potential.overall + potential.affinity(skill)
    ceiling_factor = 0.18 + 0.82 / (
        1 + math.exp(-(soft_center - score_to_rating(score)) / 4.5)
    )
    fatigue_factor = 1.0 if fatigue <= 30 else max(0.35, 1 - 0.0125 * (fatigue - 30))
    breakthrough_probability = 0.003 + 0.012 * (potential.overall / 100) ** 3
    breakthrough = _deterministic_unit(seed, week, action, repeat) < breakthrough_probability
    gained = (
        base_xp
        * _age_efficiency(age)
        * (0.75 + potential.overall / 200)
        * fatigue_factor
        * repeat_factor
        * ceiling_factor
        * (1.75 if breakthrough else 1.0)
    )
    pool = pooled_xp + gained
    multiplier = (
        0.96
        if archetype is BatterArchetype.BALANCED
        else 0.85
        if potential.affinity(skill) >= 7
        else 1.08
    )
    while pool >= _xp_threshold(score, multiplier) and score < 10:
        pool -= _xp_threshold(score, multiplier)
        score = round(min(10.0, score + 0.1), 10)
    return score, pool, gained, breakthrough


def apply_weekly_action(
    development: WeeklyDevelopment,
    scores: BatterSkillScores,
    potential: PotentialTraits,
    archetype: BatterArchetype,
    action: WeeklyAction,
    *,
    age: int,
    seed: int,
    fatigue: float = 15.0,
) -> TrainingResult:
    if not 17 <= age <= 60:
        raise ValueError("training age must be between 17 and 60")
    if not math.isfinite(fatigue) or not 0 <= fatigue <= 100:
        raise ValueError("training fatigue must be finite and between 0 and 100")
    cost = ACTION_COST[action]
    if cost > development.action_points:
        raise ValueError("weekly action points exceeded")
    rating_before = 0.0
    if action is WeeklyAction.RECOVERY:
        updated = replace(
            development,
            action_points=development.action_points - cost,
        )
        return TrainingResult(updated, scores, action, 0.0, 0.0, 0.0, False, -18.0)

    skill = {
        WeeklyAction.CONTACT: BatterSkill.CONTACT,
        WeeklyAction.POWER: BatterSkill.POWER,
        WeeklyAction.EYE: BatterSkill.EYE,
        WeeklyAction.SPEED: BatterSkill.SPEED_PROXY,
        WeeklyAction.VIDEO: BatterSkill.EYE,
        WeeklyAction.EXTRA_BP: BatterSkill.CONTACT,
    }[action]
    base_xp = {
        WeeklyAction.CONTACT: 12.0,
        WeeklyAction.POWER: 12.0,
        WeeklyAction.EYE: 12.0,
        WeeklyAction.SPEED: 7.0,
        WeeklyAction.VIDEO: 4.0,
        WeeklyAction.EXTRA_BP: 4.0,
    }[action]
    repeat_actions = {
        WeeklyAction.CONTACT,
        WeeklyAction.POWER,
        WeeklyAction.EYE,
        WeeklyAction.SPEED,
    }
    repeat = development.repeats(skill) if action in repeat_actions else 0
    rating_before = score_to_rating(scores.get(skill))
    xp_fields = [
        development.contact_xp,
        development.power_xp,
        development.eye_xp,
        development.speed_xp,
    ]
    repeat_fields = [
        development.contact_repeats,
        development.power_repeats,
        development.eye_repeats,
        development.speed_repeats,
    ]
    index = list(BatterSkill).index(skill)
    score, pool, gained, breakthrough = _train_skill(
        skill=skill,
        base_xp=base_xp,
        score=scores.get(skill),
        pooled_xp=xp_fields[index],
        repeat=repeat,
        potential=potential,
        archetype=archetype,
        age=age,
        fatigue=fatigue,
        seed=seed,
        week=development.week,
        action=action,
    )
    xp_fields[index] = pool
    result_scores = scores.with_value(skill, score)
    if action in repeat_actions:
        repeat_fields[index] += 1
    if action is WeeklyAction.EXTRA_BP:
        power_index = list(BatterSkill).index(BatterSkill.POWER)
        power_score, power_pool, power_gained, power_breakthrough = _train_skill(
            skill=BatterSkill.POWER,
            base_xp=3.0,
            score=scores.power,
            pooled_xp=xp_fields[power_index],
            repeat=0,
            potential=potential,
            archetype=archetype,
            age=age,
            fatigue=fatigue,
            seed=seed,
            week=development.week,
            action=action,
        )
        xp_fields[power_index] = power_pool
        result_scores = result_scores.with_value(BatterSkill.POWER, power_score)
        gained += power_gained
        breakthrough = breakthrough or power_breakthrough
    fatigue_gain = (
        (8, 10, 13, 16)[min(repeat, 3)]
        if cost == 2
        else 5
        if action is WeeklyAction.SPEED
        else 6
        if action is WeeklyAction.EXTRA_BP
        else 0
    )
    updated = replace(
        development,
        action_points=development.action_points - cost,
        contact_xp=xp_fields[0],
        power_xp=xp_fields[1],
        eye_xp=xp_fields[2],
        speed_xp=xp_fields[3],
        contact_repeats=repeat_fields[0],
        power_repeats=repeat_fields[1],
        eye_repeats=repeat_fields[2],
        speed_repeats=repeat_fields[3],
    )
    return TrainingResult(
        updated,
        result_scores,
        action,
        gained,
        rating_before,
        score_to_rating(score),
        breakthrough,
        float(fatigue_gain),
    )
