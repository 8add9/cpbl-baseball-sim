"""Versioned plate-appearance matchup models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from baseball_sim.ratings.mapping import rating_to_score

from .outcomes import Outcome
from .probabilities import DEFAULT_BASELINE_2021_2025, ProbabilityVector

MATCHUP_MODEL_VERSION = "pa-hierarchical-v0.1"


class MatchupModel(StrEnum):
    HIERARCHICAL = "hierarchical"
    FLAT_LOG_ODDS = "flat-log-odds"
    NAIVE_MULTIPLICATIVE = "naive-multiplicative"


@dataclass(frozen=True, slots=True)
class BatterRatings:
    contact: float = 65.0
    power: float = 65.0
    eye: float = 65.0

    def scores(self) -> tuple[float, float, float]:
        return (
            rating_to_score(self.contact),
            rating_to_score(self.power),
            rating_to_score(self.eye),
        )


@dataclass(frozen=True, slots=True)
class PitcherRatings:
    stuff: float = 65.0
    control: float = 65.0
    hr_suppression: float = 65.0

    def scores(self) -> tuple[float, float, float]:
        return (
            rating_to_score(self.stuff),
            rating_to_score(self.control),
            rating_to_score(self.hr_suppression),
        )


@dataclass(frozen=True, slots=True)
class MatchupCoefficients:
    """Grouped-binomial score slopes calibrated on completed 1990-2025 seasons."""

    eye_bb: float = 0.318166
    control_bb: float = 0.332053
    control_hbp: float = 0.183413
    contact_so: float = 0.319508
    stuff_so: float = 0.292498
    power_hr: float = 0.411641
    hr_suppression_hr: float = 0.381629
    contact_hit: float = 0.093072
    power_xbh: float = 0.133431


DEFAULT_COEFFICIENTS = MatchupCoefficients()


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    direct = math.exp(value)
    return direct / (1.0 + direct)


def _logit(probability: float) -> float:
    return math.log(probability / (1.0 - probability))


def _softmax(log_weights: list[float]) -> list[float]:
    maximum = max(log_weights)
    weights = [math.exp(value - maximum) for value in log_weights]
    total = sum(weights)
    return [value / total for value in weights]


def _scores(
    batter: BatterRatings, pitcher: PitcherRatings
) -> tuple[float, float, float, float, float, float]:
    contact, power, eye = batter.scores()
    stuff, control, hr_suppression = pitcher.scores()
    return contact, power, eye, stuff, control, hr_suppression


def hierarchical_probabilities(
    batter: BatterRatings,
    pitcher: PitcherRatings,
    coefficients: MatchupCoefficients = DEFAULT_COEFFICIENTS,
    baseline: ProbabilityVector = DEFAULT_BASELINE_2021_2025,
) -> ProbabilityVector:
    """Sequential competing-risk model with semantically isolated conditional stages."""
    contact, power, eye, stuff, control, hr_suppression = _scores(batter, pitcher)

    base_contact = 1.0 - baseline[Outcome.BB] - baseline[Outcome.HBP] - baseline[Outcome.SO]
    base_hr_cond = baseline[Outcome.HR] / base_contact
    base_non_hr_contact = base_contact - baseline[Outcome.HR]
    base_non_hr_hits = (
        baseline[Outcome.SINGLE] + baseline[Outcome.DOUBLE] + baseline[Outcome.TRIPLE]
    )
    base_hit_cond = base_non_hr_hits / base_non_hr_contact
    base_xbh_cond = (baseline[Outcome.DOUBLE] + baseline[Outcome.TRIPLE]) / base_non_hr_hits
    base_triple_cond = baseline[Outcome.TRIPLE] / (
        baseline[Outcome.DOUBLE] + baseline[Outcome.TRIPLE]
    )

    stage_a = _softmax(
        [
            math.log(baseline[Outcome.BB] / base_contact)
            + coefficients.eye_bb * eye
            - coefficients.control_bb * control,
            math.log(baseline[Outcome.HBP] / base_contact)
            - coefficients.control_hbp * control,
            math.log(baseline[Outcome.SO] / base_contact)
            - coefficients.contact_so * contact
            + coefficients.stuff_so * stuff,
            0.0,
        ]
    )
    p_bb, p_hbp, p_so, p_contact = stage_a
    p_hr_cond = _sigmoid(
        _logit(base_hr_cond)
        + coefficients.power_hr * power
        - coefficients.hr_suppression_hr * hr_suppression
    )
    p_hit_cond = _sigmoid(_logit(base_hit_cond) + coefficients.contact_hit * contact)
    p_xbh_cond = _sigmoid(_logit(base_xbh_cond) + coefficients.power_xbh * power)

    p_hr = p_contact * p_hr_cond
    p_non_hr_contact = p_contact * (1.0 - p_hr_cond)
    p_non_hr_hit = p_non_hr_contact * p_hit_cond
    p_out = p_non_hr_contact * (1.0 - p_hit_cond)
    p_xbh = p_non_hr_hit * p_xbh_cond
    p_single = p_non_hr_hit * (1.0 - p_xbh_cond)
    p_triple = p_xbh * base_triple_cond
    p_double = p_xbh * (1.0 - base_triple_cond)

    return ProbabilityVector.from_mapping(
        {
            Outcome.BB: p_bb,
            Outcome.HBP: p_hbp,
            Outcome.SO: p_so,
            Outcome.OUT: p_out,
            Outcome.SINGLE: p_single,
            Outcome.DOUBLE: p_double,
            Outcome.TRIPLE: p_triple,
            Outcome.HR: p_hr,
        }
    )


def flat_log_odds_probabilities(
    batter: BatterRatings,
    pitcher: PitcherRatings,
    coefficients: MatchupCoefficients = DEFAULT_COEFFICIENTS,
    baseline: ProbabilityVector = DEFAULT_BASELINE_2021_2025,
) -> ProbabilityVector:
    """Comparator: one multinomial softmax, which intentionally exposes cross-talk."""
    contact, power, eye, stuff, control, hr_suppression = _scores(batter, pitcher)
    effects = {
        Outcome.BB: coefficients.eye_bb * eye - coefficients.control_bb * control,
        Outcome.HBP: -coefficients.control_hbp * control,
        Outcome.SO: -coefficients.contact_so * contact + coefficients.stuff_so * stuff,
        Outcome.OUT: -0.5 * coefficients.contact_hit * contact,
        Outcome.SINGLE: coefficients.contact_hit * contact,
        Outcome.DOUBLE: coefficients.contact_hit * contact + coefficients.power_xbh * power,
        Outcome.TRIPLE: coefficients.contact_hit * contact + 0.5 * coefficients.power_xbh * power,
        Outcome.HR: coefficients.power_hr * power
        - coefficients.hr_suppression_hr * hr_suppression,
    }
    log_weights = [math.log(baseline[outcome]) + effects[outcome] for outcome in Outcome]
    return ProbabilityVector(tuple(_softmax(log_weights)))


def naive_multiplicative_probabilities(
    batter: BatterRatings,
    pitcher: PitcherRatings,
    coefficients: MatchupCoefficients = DEFAULT_COEFFICIENTS,
    baseline: ProbabilityVector = DEFAULT_BASELINE_2021_2025,
) -> ProbabilityVector:
    """Negative-control comparator using clipped linear multipliers and renormalization."""
    contact, power, eye, stuff, control, hr_suppression = _scores(batter, pitcher)
    effects = (
        coefficients.eye_bb * eye - coefficients.control_bb * control,
        -coefficients.control_hbp * control,
        -coefficients.contact_so * contact + coefficients.stuff_so * stuff,
        -0.5 * coefficients.contact_hit * contact,
        coefficients.contact_hit * contact,
        coefficients.contact_hit * contact + coefficients.power_xbh * power,
        coefficients.contact_hit * contact + 0.5 * coefficients.power_xbh * power,
        coefficients.power_hr * power - coefficients.hr_suppression_hr * hr_suppression,
    )
    weights = [
        baseline[outcome] * max(0.05, 1.0 + effect)
        for outcome, effect in zip(Outcome, effects, strict=True)
    ]
    return ProbabilityVector.normalized(weights)


def matchup_probabilities(
    batter: BatterRatings,
    pitcher: PitcherRatings,
    model: MatchupModel = MatchupModel.HIERARCHICAL,
    coefficients: MatchupCoefficients = DEFAULT_COEFFICIENTS,
) -> ProbabilityVector:
    if model is MatchupModel.HIERARCHICAL:
        return hierarchical_probabilities(batter, pitcher, coefficients)
    if model is MatchupModel.FLAT_LOG_ODDS:
        return flat_log_odds_probabilities(batter, pitcher, coefficients)
    if model is MatchupModel.NAIVE_MULTIPLICATIVE:
        return naive_multiplicative_probabilities(batter, pitcher, coefficients)
    raise ValueError(f"unsupported matchup model: {model}")
