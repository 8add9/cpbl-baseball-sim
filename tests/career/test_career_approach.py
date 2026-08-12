from __future__ import annotations

from baseball_sim.career.approach import (
    BattingApproach,
    CareerBattingContext,
    career_matchup_probabilities,
)
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings, matchup_probabilities
from baseball_sim.simulation.outcomes import Outcome

PITCHER = PitcherRatings(65, 65, 65)


def test_normal_is_bit_exact_shared_engine_and_probabilities_remain_valid() -> None:
    batter = BatterRatings(65, 65, 65)
    assert career_matchup_probabilities(batter, PITCHER) == matchup_probabilities(batter, PITCHER)
    for approach in BattingApproach:
        probabilities = career_matchup_probabilities(batter, PITCHER, approach)
        assert abs(sum(probabilities.as_dict().values()) - 1) < 1e-12
        assert all(0 <= value <= 1 for value in probabilities.as_dict().values())


def test_approaches_have_expected_directions_and_interact_with_ability() -> None:
    neutral = BatterRatings(65, 65, 65)
    base = career_matchup_probabilities(neutral, PITCHER)
    power = career_matchup_probabilities(neutral, PITCHER, BattingApproach.POWER)
    contact = career_matchup_probabilities(neutral, PITCHER, BattingApproach.CONTACT)
    patient = career_matchup_probabilities(neutral, PITCHER, BattingApproach.PATIENT)
    assert power[Outcome.HR] > base[Outcome.HR]
    assert power[Outcome.SO] > base[Outcome.SO]
    assert contact[Outcome.SO] < base[Outcome.SO]
    assert contact[Outcome.HR] < base[Outcome.HR]
    assert patient[Outcome.BB] > base[Outcome.BB]

    low = BatterRatings(65, 55, 65)
    elite = BatterRatings(65, 100, 65)
    low_lift = (
        career_matchup_probabilities(low, PITCHER, BattingApproach.POWER)[Outcome.HR]
        / career_matchup_probabilities(low, PITCHER)[Outcome.HR]
    )
    elite_lift = (
        career_matchup_probabilities(elite, PITCHER, BattingApproach.POWER)[Outcome.HR]
        / career_matchup_probabilities(elite, PITCHER)[Outcome.HR]
    )
    assert elite_lift != low_lift


def test_fatigue_is_temporary_and_reduces_effective_results() -> None:
    batter = BatterRatings(70, 70, 70)
    fresh = career_matchup_probabilities(batter, PITCHER)
    tired = career_matchup_probabilities(batter, PITCHER, context=CareerBattingContext(fatigue=90))
    assert tired[Outcome.SO] > fresh[Outcome.SO]
    assert tired[Outcome.HR] < fresh[Outcome.HR]


def test_extreme_cards_and_condition_remain_finite_probability_vectors() -> None:
    for rating in (30.000001, 109.999999):
        batter = BatterRatings(rating, rating, rating)
        for approach in BattingApproach:
            vector = career_matchup_probabilities(
                batter,
                PITCHER,
                approach,
                CareerBattingContext(fatigue=100, form_latent=-2),
            )
            assert abs(sum(vector.as_dict().values()) - 1) < 1e-12
            assert all(0 <= value <= 1 for value in vector.as_dict().values())
