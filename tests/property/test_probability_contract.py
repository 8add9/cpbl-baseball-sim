from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.simulation.outcomes import Outcome
from baseball_sim.simulation.probabilities import ProbabilityVector


@given(
    st.lists(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=len(Outcome),
        max_size=len(Outcome),
    ).filter(lambda values: sum(values) > 0)
)
def test_normalized_probability_vector_is_finite_bounded_and_sums_to_one(
    weights: list[float],
) -> None:
    vector = ProbabilityVector.normalized(weights)
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in vector)
    assert sum(vector) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(
    "weights",
    [([0.0] * len(Outcome)), ([-1.0] + [1.0] * (len(Outcome) - 1))],
)
def test_invalid_probability_weights_are_rejected(weights: list[float]) -> None:
    with pytest.raises(ValueError):
        ProbabilityVector.normalized(weights)
