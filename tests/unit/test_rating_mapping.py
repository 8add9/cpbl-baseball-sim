from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.ratings.mapping import rating_display, rating_to_score, score_to_rating


@pytest.mark.parametrize("score", [-10, -5, -1, 0, 1, 5, 10, 20])
def test_mapping_has_open_bounds_and_neutral_center(score: float) -> None:
    rating = score_to_rating(score)
    assert 30 < rating < 110
    if score == 0:
        assert rating == 65


@given(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False))
def test_mapping_round_trip(score: float) -> None:
    assert rating_to_score(score_to_rating(score)) == pytest.approx(score, abs=1e-6)


@given(
    st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1e-4, max_value=5, allow_nan=False, allow_infinity=False),
)
def test_mapping_is_strictly_monotonic(score: float, delta: float) -> None:
    assert score_to_rating(score + delta) > score_to_rating(score)


def test_display_rounds_half_up_but_is_not_an_inverse() -> None:
    assert rating_display(65.49) == 65
    assert rating_display(65.50) == 66
    assert math.isclose(rating_to_score(65), 0.0)


@pytest.mark.parametrize("rating", [30, 110, math.nan, math.inf])
def test_inverse_rejects_asymptotes_and_non_finite_values(rating: float) -> None:
    with pytest.raises(ValueError):
        rating_to_score(rating)
