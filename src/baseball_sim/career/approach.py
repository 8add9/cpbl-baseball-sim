"""Career batting approaches as inputs to the accepted PA probability engine."""

from __future__ import annotations

from enum import StrEnum

from baseball_sim.ratings.mapping import rating_to_score, score_to_rating
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings, matchup_probabilities
from baseball_sim.simulation.probabilities import ProbabilityVector

from .condition import CareerCondition

APPROACH_MODEL_VERSION = "career-approach-v0.1"
_MIN_EFFECTIVE_RATING = 30.000001
_MAX_EFFECTIVE_RATING = 109.999999


class BattingApproach(StrEnum):
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    PATIENT = "patient"
    POWER = "power_swing"
    CONTACT = "contact"
    SITUATIONAL = "situational"


CareerBattingContext = CareerCondition
NEUTRAL_CONTEXT = CareerCondition(fatigue=0.0)


def _effective_batter(
    batter: BatterRatings, approach: BattingApproach, context: CareerBattingContext
) -> BatterRatings:
    contact = rating_to_score(batter.contact)
    power = rating_to_score(batter.power)
    eye = rating_to_score(batter.eye)
    if approach is BattingApproach.POWER:
        contact -= 0.20
        eye -= 0.10
        power += 0.25 + 0.05 * max(power, 0)
    elif approach is BattingApproach.CONTACT:
        contact += 0.22 + 0.04 * max(contact, 0)
        power -= 0.28
        eye += 0.03
    elif approach is BattingApproach.PATIENT:
        contact -= 0.08
        power -= 0.05
        eye += 0.20 + 0.04 * max(eye, 0)
    elif approach is BattingApproach.AGGRESSIVE:
        contact += 0.10 + 0.02 * max(contact, 0)
        power += 0.05
        eye -= 0.25
    elif approach is BattingApproach.SITUATIONAL:
        contact += 0.14
        power -= 0.35
        eye += 0.05
    fatigue = max(0.0, context.fatigue - 40)
    contact_rating = score_to_rating(contact) - 0.05 * fatigue + 0.60 * context.form_latent
    power_rating = score_to_rating(power) - 0.04 * fatigue + 0.35 * context.form_latent
    eye_rating = score_to_rating(eye) - 0.05 * fatigue + 0.60 * context.form_latent
    # Temporary condition can push an extreme historical card beyond the mapping's
    # open interval. Clamp only the effective game input; permanent Score is untouched.
    return BatterRatings(
        min(_MAX_EFFECTIVE_RATING, max(_MIN_EFFECTIVE_RATING, contact_rating)),
        min(_MAX_EFFECTIVE_RATING, max(_MIN_EFFECTIVE_RATING, power_rating)),
        min(_MAX_EFFECTIVE_RATING, max(_MIN_EFFECTIVE_RATING, eye_rating)),
    )


def career_matchup_probabilities(
    batter: BatterRatings,
    pitcher: PitcherRatings,
    approach: BattingApproach = BattingApproach.NORMAL,
    context: CareerBattingContext = NEUTRAL_CONTEXT,
) -> ProbabilityVector:
    """Delegate every Career PA to the one accepted hierarchical matchup model."""
    if approach is BattingApproach.NORMAL and context == NEUTRAL_CONTEXT:
        return matchup_probabilities(batter, pitcher)
    return matchup_probabilities(_effective_batter(batter, approach, context), pitcher)
