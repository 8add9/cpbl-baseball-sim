"""Frozen B_QuadraticTanh mapping shared by batter and pitcher ratings."""

from __future__ import annotations

import math

RATING_MIN = 30.0
RATING_NEUTRAL = 65.0
RATING_MAX = 110.0
MAPPING_VERSION = "B_QuadraticTanh-v1"


def score_to_rating(score: float) -> float:
    """Map a finite final score to the open rating interval (30, 110)."""
    if not math.isfinite(score):
        raise ValueError("score must be finite")
    if score >= 0:
        return 65.0 + 45.0 * math.tanh(0.16 * score + 0.01 * score * score)
    t = -score
    return 65.0 - 35.0 * math.tanh((36.0 / 175.0) * t + 0.04 * t * t)


def rating_to_score(rating: float) -> float:
    """Invert B_QuadraticTanh for a raw rating strictly between 30 and 110."""
    if not math.isfinite(rating) or not RATING_MIN < rating < RATING_MAX:
        raise ValueError("raw rating must be finite and strictly between 30 and 110")
    if rating >= RATING_NEUTRAL:
        u = math.atanh((rating - 65.0) / 45.0)
        return (-0.16 + math.sqrt(0.16**2 + 0.04 * u)) / 0.02
    v = math.atanh((65.0 - rating) / 35.0)
    t = (-(36.0 / 175.0) + math.sqrt((36.0 / 175.0) ** 2 + 0.16 * v)) / 0.08
    return -t


def rating_display(rating_raw: float) -> int:
    """Round a positive raw rating half-up for UI display only."""
    if not math.isfinite(rating_raw) or not RATING_MIN <= rating_raw <= RATING_MAX:
        raise ValueError("rating must be finite and within [30, 110]")
    return math.floor(rating_raw + 0.5)
