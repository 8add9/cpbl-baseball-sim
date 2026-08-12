from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.career.condition import (
    CareerActivity,
    CareerCondition,
    Injury,
    InjurySeverity,
    advance_day,
    apply_activity,
    injury_probability,
    roll_injury,
    training_efficiency,
    update_form,
)


@given(
    fatigue=st.floats(min_value=0, max_value=100, allow_nan=False),
    activity=st.sampled_from(list(CareerActivity)),
)
def test_activity_and_daily_recovery_keep_fatigue_bounded(
    fatigue: float, activity: CareerActivity
) -> None:
    condition = CareerCondition(fatigue=fatigue)
    result = advance_day(apply_activity(condition, activity))
    assert 0 <= result.fatigue <= 100


def test_form_is_small_bounded_mean_reverting_and_replayable() -> None:
    hot = CareerCondition(form_latent=2.0)
    first = update_form(hot, 0, seed=91, week=7)
    assert first == update_form(hot, 0, seed=91, week=7)
    assert -2 <= first.form_latent <= 2


def test_injury_probability_and_roll_are_deterministic() -> None:
    assert injury_probability(20) < injury_probability(80) < injury_probability(100)
    assert injury_probability(100, intense_training=True) > injury_probability(100)
    condition = CareerCondition(fatigue=100)
    injured = next(
        result
        for counter in range(10_000)
        if (result := roll_injury(condition, seed=44, counter=counter)).injury is not None
    )
    replayed = next(
        result
        for counter in range(10_000)
        if (result := roll_injury(condition, seed=44, counter=counter)).injury is not None
    )
    assert injured == replayed
    assert injured.injury is not None
    assert 1 <= injured.injury.days_remaining <= 28


def test_injury_blocks_activity_and_recovers_exactly() -> None:
    condition = CareerCondition(injury=Injury(InjurySeverity.DAY_TO_DAY, 2))
    with pytest.raises(ValueError, match="injured"):
        apply_activity(condition, CareerActivity.STARTER_GAME)
    assert advance_day(advance_day(condition)).injury is None
    assert training_efficiency(condition) == 0
    assert training_efficiency(replace(condition, injury=None, fatigue=100)) == 0.35


def test_week_and_multiweek_injuries_can_count_down_to_available() -> None:
    for injury in (
        Injury(InjurySeverity.ONE_WEEK, 7),
        Injury(InjurySeverity.MULTI_WEEK, 28),
    ):
        condition = CareerCondition(injury=injury)
        for _ in range(injury.days_remaining):
            condition = advance_day(condition)
        assert condition.injury is None
