from __future__ import annotations

import pytest

from baseball_sim.simulation.outcomes import Outcome
from baseball_sim.simulation.probabilities import DEFAULT_BASELINE_2021_2025


def test_audited_2021_2025_neutral_baseline() -> None:
    expected = {
        Outcome.BB: 0.075000,
        Outcome.HBP: 0.013106,
        Outcome.SO: 0.171333,
        Outcome.OUT: 0.508316,
        Outcome.SINGLE: 0.176035,
        Outcome.DOUBLE: 0.038540,
        Outcome.TRIPLE: 0.004296,
        Outcome.HR: 0.013374,
    }
    assert DEFAULT_BASELINE_2021_2025.as_dict() == {
        outcome.value: pytest.approx(value) for outcome, value in expected.items()
    }
