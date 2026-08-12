from __future__ import annotations

import pytest

from baseball_sim.career import (
    BatterArchetype,
    WeeklyAction,
    WeeklyDevelopment,
    apply_weekly_action,
    archetype_potential_traits,
)
from baseball_sim.career.condition import CareerActivity, CareerCondition, apply_activity
from baseball_sim.career.models import ARCHETYPE_SCORES


def test_every_archetype_has_the_same_starting_score_budget() -> None:
    assert all(scores.total == pytest.approx(-2.4) for scores in ARCHETYPE_SCORES.values())


def test_weekly_ap_training_xp_fatigue_and_recovery_are_server_rules() -> None:
    development = WeeklyDevelopment()
    scores = ARCHETYPE_SCORES[BatterArchetype.POWER]
    potential = archetype_potential_traits(BatterArchetype.POWER)
    first = apply_weekly_action(
        development,
        scores,
        potential,
        BatterArchetype.POWER,
        WeeklyAction.POWER,
        age=18,
        seed=42,
    )
    second = apply_weekly_action(
        first.development,
        first.scores,
        potential,
        BatterArchetype.POWER,
        WeeklyAction.POWER,
        age=18,
        seed=42,
    )
    assert first.development.action_points == 2
    assert second.development.action_points == 0
    assert first.xp_gained > second.xp_gained
    assert first.fatigue_delta == 8
    assert second.fatigue_delta == 10
    assert apply_activity(CareerCondition(), CareerActivity.FOCUSED_TRAINING).fatigue == 23
    with pytest.raises(ValueError, match="action points"):
        apply_weekly_action(
            second.development,
            second.scores,
            potential,
            BatterArchetype.POWER,
            WeeklyAction.RECOVERY,
            age=18,
            seed=42,
        )


def test_speed_archetype_is_distinct_and_speed_training_uses_latent_xp() -> None:
    scores = ARCHETYPE_SCORES[BatterArchetype.SPEED]
    result = apply_weekly_action(
        WeeklyDevelopment(),
        scores,
        archetype_potential_traits(BatterArchetype.SPEED),
        BatterArchetype.SPEED,
        WeeklyAction.SPEED,
        age=18,
        seed=7,
    )
    assert result.development.speed_xp > 0
    assert result.development.action_points == 3
    assert scores.speed_proxy > max(scores.contact, scores.power, scores.eye)


def test_extra_bp_trains_contact_and_power_while_video_does_not_add_fatigue() -> None:
    scores = ARCHETYPE_SCORES[BatterArchetype.BALANCED]
    potential = archetype_potential_traits(BatterArchetype.BALANCED)
    bp = apply_weekly_action(
        WeeklyDevelopment(),
        scores,
        potential,
        BatterArchetype.BALANCED,
        WeeklyAction.EXTRA_BP,
        age=18,
        seed=8,
    )
    assert bp.development.contact_xp > 0
    assert bp.development.power_xp > 0
    assert bp.fatigue_delta == 6
    video = apply_weekly_action(
        WeeklyDevelopment(),
        scores,
        potential,
        BatterArchetype.BALANCED,
        WeeklyAction.VIDEO,
        age=18,
        seed=8,
    )
    assert video.development.eye_xp > 0
    assert video.fatigue_delta == 0


@pytest.mark.parametrize("invalid_xp", [-1.0, float("nan"), float("inf")])
def test_weekly_development_rejects_invalid_saved_xp(invalid_xp: float) -> None:
    with pytest.raises(ValueError, match="skill XP"):
        WeeklyDevelopment(contact_xp=invalid_xp)


@pytest.mark.parametrize("invalid_repeats", [-1, 1.5])
def test_weekly_development_rejects_invalid_repeat_counts(
    invalid_repeats: int | float,
) -> None:
    with pytest.raises(ValueError, match="repeat counts"):
        WeeklyDevelopment(contact_repeats=invalid_repeats)  # type: ignore[arg-type]


@pytest.mark.parametrize("fatigue", [-1.0, 101.0, float("nan")])
def test_training_rejects_invalid_condition_input(fatigue: float) -> None:
    with pytest.raises(ValueError, match="fatigue"):
        apply_weekly_action(
            WeeklyDevelopment(),
            ARCHETYPE_SCORES[BatterArchetype.BALANCED],
            archetype_potential_traits(BatterArchetype.BALANCED),
            BatterArchetype.BALANCED,
            WeeklyAction.VIDEO,
            age=18,
            seed=1,
            fatigue=fatigue,
        )
