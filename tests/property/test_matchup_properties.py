from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.simulation.matchup import (
    BatterRatings,
    MatchupModel,
    PitcherRatings,
    matchup_probabilities,
)
from baseball_sim.simulation.outcomes import Outcome
from baseball_sim.simulation.sampling import analytic_line

RATINGS = st.floats(min_value=30.01, max_value=109.99, allow_nan=False, allow_infinity=False)


@given(contact=RATINGS, power=RATINGS, eye=RATINGS, stuff=RATINGS, control=RATINGS, hr=RATINGS)
@pytest.mark.parametrize("model", list(MatchupModel))
def test_every_model_returns_a_valid_probability_vector(
    model: MatchupModel,
    contact: float,
    power: float,
    eye: float,
    stuff: float,
    control: float,
    hr: float,
) -> None:
    probabilities = matchup_probabilities(
        BatterRatings(contact, power, eye), PitcherRatings(stuff, control, hr), model
    )
    assert math.isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities)


@pytest.mark.parametrize("low,high", [(50.0, 65.0), (65.0, 80.0), (80.0, 95.0), (95.0, 105.0)])
def test_hierarchical_primary_effects_are_monotone(low: float, high: float) -> None:
    neutral_batter = BatterRatings()
    neutral_pitcher = PitcherRatings()

    low_power = matchup_probabilities(BatterRatings(power=low), neutral_pitcher)
    high_power = matchup_probabilities(BatterRatings(power=high), neutral_pitcher)
    assert high_power[Outcome.HR] > low_power[Outcome.HR]
    assert analytic_line(high_power, 100_000)["SLG"] > analytic_line(low_power, 100_000)["SLG"]

    low_contact = matchup_probabilities(BatterRatings(contact=low), neutral_pitcher)
    high_contact = matchup_probabilities(BatterRatings(contact=high), neutral_pitcher)
    assert high_contact[Outcome.SO] < low_contact[Outcome.SO]
    assert analytic_line(high_contact, 100_000)["AVG"] > analytic_line(low_contact, 100_000)["AVG"]

    assert matchup_probabilities(BatterRatings(eye=high), neutral_pitcher)[Outcome.BB] > (
        matchup_probabilities(BatterRatings(eye=low), neutral_pitcher)[Outcome.BB]
    )
    assert matchup_probabilities(neutral_batter, PitcherRatings(stuff=high))[Outcome.SO] > (
        matchup_probabilities(neutral_batter, PitcherRatings(stuff=low))[Outcome.SO]
    )
    assert matchup_probabilities(neutral_batter, PitcherRatings(control=high))[Outcome.BB] < (
        matchup_probabilities(neutral_batter, PitcherRatings(control=low))[Outcome.BB]
    )
    assert matchup_probabilities(
        neutral_batter, PitcherRatings(hr_suppression=high)
    )[Outcome.HR] < matchup_probabilities(
        neutral_batter, PitcherRatings(hr_suppression=low)
    )[Outcome.HR]


def test_power_does_not_change_earlier_hierarchical_stages() -> None:
    neutral = matchup_probabilities(BatterRatings(power=65.0), PitcherRatings())
    elite = matchup_probabilities(BatterRatings(power=100.0), PitcherRatings())
    for outcome in (Outcome.BB, Outcome.HBP, Outcome.SO):
        assert elite[outcome] == neutral[outcome]
