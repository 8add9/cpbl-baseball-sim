from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.career.team_status import (
    CompetitionLevel,
    ParticipationRole,
    TeamStanding,
    TeamStatus,
    decide_participation,
    evaluate_status,
    readiness_score,
    start_probability,
    update_coach_trust,
)


@given(
    trust=st.floats(min_value=0, max_value=100, allow_nan=False),
    performance=st.floats(min_value=-100, max_value=100, allow_nan=False),
    discipline=st.floats(min_value=-100, max_value=100, allow_nan=False),
    availability=st.floats(min_value=-100, max_value=100, allow_nan=False),
)
def test_trust_is_bounded_and_weekly_delta_is_capped(
    trust: float, performance: float, discipline: float, availability: float
) -> None:
    before = TeamStanding(coach_trust=trust)
    after = update_coach_trust(
        before,
        performance_z=performance,
        discipline=discipline,
        availability=availability,
    )
    assert 0 <= after.coach_trust <= 100
    assert abs(after.coach_trust - trust) <= 4.0 + 1e-12


def test_status_requires_two_promotion_and_three_demotion_weeks() -> None:
    standing = TeamStanding(coach_trust=80)
    standing = evaluate_status(standing, 33)
    assert standing.status is TeamStatus.MINOR_BENCH
    standing = evaluate_status(standing, 33)
    assert standing.status is TeamStatus.MINOR_STARTER

    standing = evaluate_status(standing, 20)
    standing = evaluate_status(standing, 20)
    assert standing.status is TeamStatus.MINOR_STARTER
    standing = evaluate_status(standing, 20)
    assert standing.status is TeamStatus.MINOR_BENCH


def test_readiness_combines_inputs_and_high_fatigue_hurts() -> None:
    standing = TeamStanding(coach_trust=70)
    fresh = readiness_score(
        standing,
        ability_percentile=70,
        performance_percentile=60,
        position_need=50,
        fatigue=20,
    )
    tired = readiness_score(
        standing,
        ability_percentile=70,
        performance_percentile=60,
        position_need=50,
        fatigue=100,
    )
    assert fresh == 65.0
    assert tired == 59.0


def test_participation_is_seed_replayable_and_injury_fails_closed() -> None:
    standing = TeamStanding(80, TeamStatus.MAJOR_STARTER)
    kwargs = dict(
        fatigue=30,
        form_latent=0.5,
        depth_penalty=0.05,
        speed_rating=75,
        injured=False,
        seed=2026,
        game_number=17,
    )
    first = decide_participation(standing, **kwargs)
    assert first == decide_participation(standing, **kwargs)
    assert first.level is CompetitionLevel.MAJOR
    injured = decide_participation(standing, **{**kwargs, "injured": True})
    assert injured.role is ParticipationRole.NO_APPEARANCE
    assert injured.start_probability == 0


def test_star_is_more_likely_to_start_than_bench_and_fatigue_reduces_chance() -> None:
    bench = start_probability(
        TeamStanding(50, TeamStatus.MAJOR_BENCH),
        fatigue=20,
        form_latent=0,
        depth_penalty=0,
    )
    star = start_probability(
        TeamStanding(50, TeamStatus.STAR),
        fatigue=20,
        form_latent=0,
        depth_penalty=0,
    )
    tired_star = start_probability(
        TeamStanding(50, TeamStatus.STAR),
        fatigue=100,
        form_latent=0,
        depth_penalty=0,
    )
    assert star > bench
    assert tired_star < star
