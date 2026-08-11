from __future__ import annotations

import numpy as np
import pytest

from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings, matchup_probabilities
from baseball_sim.simulation.outcomes import Outcome
from baseball_sim.simulation.sampling import analytic_line, simulate_plate_appearances


@pytest.mark.monte_carlo
def test_power_100_materially_changes_hr_and_slg_at_100k_pa() -> None:
    neutral = matchup_probabilities(BatterRatings(power=65.0), PitcherRatings())
    elite = matchup_probabilities(BatterRatings(power=100.0), PitcherRatings())
    neutral_expected = analytic_line(neutral, 100_000)
    elite_expected = analytic_line(elite, 100_000)

    assert elite_expected["HR"] - neutral_expected["HR"] >= 0.005
    assert elite_expected["SLG"] - neutral_expected["SLG"] >= 0.050

    seed = 20260811
    neutral_sample = simulate_plate_appearances(neutral, 100_000, np.random.default_rng(seed))
    elite_sample = simulate_plate_appearances(elite, 100_000, np.random.default_rng(seed))
    assert elite_sample.count(Outcome.HR) - neutral_sample.count(Outcome.HR) >= 500
    assert elite_sample.slg - neutral_sample.slg >= 0.045
