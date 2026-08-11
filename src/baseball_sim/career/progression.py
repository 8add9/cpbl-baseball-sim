"""Versioned score-authoritative batter development purchases."""

from __future__ import annotations

import math
from dataclasses import replace

from .models import BatterArchetype, BatterSkill, CareerState, RatingImprovedEvent

SCORE_INCREMENT = 0.1
SEASON_PURCHASE_CAP = 12
ABILITY_PURCHASE_CAP = 4
DEVELOPMENT_BANK_CAP = 24


def _primary_skill(archetype: BatterArchetype) -> BatterSkill | None:
    return {
        BatterArchetype.CONTACT: BatterSkill.CONTACT,
        BatterArchetype.POWER: BatterSkill.POWER,
        BatterArchetype.PATIENT: BatterSkill.EYE,
        BatterArchetype.BALANCED: None,
    }[archetype]


def purchase_multiplier(archetype: BatterArchetype, skill: BatterSkill) -> float:
    if archetype is BatterArchetype.BALANCED:
        return 0.95
    return 0.85 if skill is _primary_skill(archetype) else 1.10


def purchase_cost(state: CareerState, skill: BatterSkill) -> int:
    if skill is BatterSkill.SPEED_PROXY:
        raise ValueError("SpeedProxy is read-only in Career v0.3")
    score = state.scores.get(skill)
    multiplier = purchase_multiplier(state.origin.profile.archetype, skill)
    return math.ceil(multiplier * (1.0 + max(score, 0.0) ** 2 / 3.0))


def spend_development_points(
    state: CareerState, skill: BatterSkill, purchases: int = 1
) -> CareerState:
    """Buy +0.1 Score steps under potential, seasonal and bank constraints."""
    if purchases <= 0:
        raise ValueError("purchases must be positive")
    if state.retired:
        raise ValueError("the career is retired")
    if state.active_game is not None:
        raise ValueError("training is unavailable during an active game")
    if skill is BatterSkill.SPEED_PROXY:
        raise ValueError("SpeedProxy is read-only in Career v0.3")
    skill_index = list(BatterSkill).index(skill)
    if state.season_purchases + purchases > SEASON_PURCHASE_CAP:
        raise ValueError("season purchase cap exceeded")
    if state.season_skill_purchases[skill_index] + purchases > ABILITY_PURCHASE_CAP:
        raise ValueError("ability purchase cap exceeded")

    working_score = state.scores.get(skill)
    potential = state.origin.potential_scores.get(skill)
    total_cost = 0
    for _ in range(purchases):
        if working_score + SCORE_INCREMENT > potential + 1e-12:
            raise ValueError("ability potential reached")
        multiplier = purchase_multiplier(state.origin.profile.archetype, skill)
        total_cost += math.ceil(multiplier * (1.0 + max(working_score, 0.0) ** 2 / 3.0))
        working_score = round(working_score + SCORE_INCREMENT, 10)
    if total_cost > state.development_points:
        raise ValueError("insufficient development points")

    counters = list(state.season_skill_purchases)
    counters[skill_index] += purchases
    before = state.scores.get(skill)
    event = RatingImprovedEvent(skill, purchases, total_cost, before, working_score)
    return replace(
        state,
        development_points=state.development_points - total_cost,
        scores=state.scores.with_value(skill, working_score),
        season_purchases=state.season_purchases + purchases,
        season_skill_purchases=(counters[0], counters[1], counters[2], counters[3]),
        events=state.events + (event,),
    )
