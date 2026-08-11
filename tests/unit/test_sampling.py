from __future__ import annotations

import numpy as np

from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings, matchup_probabilities
from baseball_sim.simulation.sampling import simulate_plate_appearances


def test_same_seed_produces_identical_counts() -> None:
    probabilities = matchup_probabilities(BatterRatings(power=100.0), PitcherRatings())
    first = simulate_plate_appearances(probabilities, 100_000, np.random.default_rng(1234))
    second = simulate_plate_appearances(probabilities, 100_000, np.random.default_rng(1234))
    assert first == second


def test_different_seed_changes_counts() -> None:
    probabilities = matchup_probabilities(BatterRatings(), PitcherRatings())
    first = simulate_plate_appearances(probabilities, 100_000, np.random.default_rng(1))
    second = simulate_plate_appearances(probabilities, 100_000, np.random.default_rng(2))
    assert first != second
