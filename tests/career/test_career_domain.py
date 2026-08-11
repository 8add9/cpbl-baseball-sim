from __future__ import annotations

from dataclasses import replace

import pytest

from baseball_sim.career import (
    BatterArchetype,
    BatterSkill,
    BattingStats,
    GamePlayedEvent,
    Handedness,
    advance_season,
    create_career,
    next_pa,
    play_game,
    purchase_cost,
    replay_career,
    simulate_games,
    simulate_season,
    simulate_to_next_event,
    simulate_to_season_end,
    simulate_week,
    spend_development_points,
)


def _career(
    archetype: BatterArchetype = BatterArchetype.BALANCED,
    *,
    seed: int = 42,
    season_games: int = 6,
):
    return create_career(
        player_id="career-1",
        name="Career Batter",
        position="OF",
        bats=Handedness.LEFT,
        throws=Handedness.RIGHT,
        archetype=archetype,
        age=18,
        season_year=2026,
        seed=seed,
        season_games=season_games,
    )


def test_archetypes_create_distinct_frozen_batter_profiles() -> None:
    contact = _career(BatterArchetype.CONTACT)
    power = _career(BatterArchetype.POWER)
    patient = _career(BatterArchetype.PATIENT)
    balanced = _career(BatterArchetype.BALANCED)
    assert contact.ratings.contact > contact.ratings.power
    assert power.ratings.power > power.ratings.contact
    assert patient.ratings.eye > patient.ratings.power
    assert balanced.ratings.contact == balanced.ratings.power == balanced.ratings.eye
    assert balanced.ratings.speed_proxy == balanced.ratings.contact
    assert balanced.ratings.contact < 65
    assert contact.scores.total == pytest.approx(-2.4)
    assert power.scores.total == pytest.approx(-2.4)
    assert patient.scores.total == pytest.approx(-2.4)
    assert balanced.scores.total == pytest.approx(-2.4)
    assert contact.origin.potential_scores.contact == 6.5
    assert contact.origin.potential_scores.power == 5.0
    assert balanced.origin.potential_scores.contact == 5.5


def test_creation_validates_identity_age_schedule_and_handedness() -> None:
    with pytest.raises(ValueError, match="name"):
        replace(_career().origin.profile, name=" ")
    with pytest.raises(ValueError, match="age 18"):
        replace(_career().origin, starting_age=12)
    with pytest.raises(ValueError, match="season_games"):
        replace(_career().origin, season_games=0)
    with pytest.raises(ValueError, match="throws"):
        replace(_career().origin.profile, throws=Handedness.SWITCH)


def test_one_game_updates_season_and_career_stats_and_rewards() -> None:
    state = play_game(_career(), plate_appearances=5)
    assert state.games_played == 1
    assert state.season_stats.games == state.career_stats.games == 1
    assert state.season_stats.pa == state.career_stats.pa == state.experience
    assert state.season_stats.pa >= 3
    assert state.season_stats.pa == (
        state.season_stats.ab + state.season_stats.walks + state.season_stats.hbp
    )
    assert state.experience > 0
    assert len(state.events) > state.season_stats.pa
    assert len([event for event in state.events if isinstance(event, GamePlayedEvent)]) == 1


def test_game_and_batch_simulation_are_seed_deterministic() -> None:
    assert simulate_games(_career(seed=42), 5) == simulate_games(_career(seed=42), 5)
    first = simulate_games(_career(seed=42), 5)
    second = simulate_games(_career(seed=43), 5)
    first_games = [event.outcomes for event in first.events if isinstance(event, GamePlayedEvent)]
    second_games = [event.outcomes for event in second.events if isinstance(event, GamePlayedEvent)]
    assert first_games != second_games


def test_schedule_controls_do_not_overrun_and_season_advances_age() -> None:
    partial = simulate_games(_career(season_games=4), 2)
    completed = simulate_to_season_end(partial)
    assert completed.games_played == 4
    with pytest.raises(ValueError, match="complete"):
        play_game(completed)

    next_year = advance_season(completed)
    assert next_year.age == 19
    assert next_year.season_year == 2027
    assert next_year.games_played == 0
    assert next_year.season_stats.games == 0
    assert next_year.season_purchases == 0
    assert next_year.season_skill_purchases == (0, 0, 0, 0)
    assert next_year.career_stats.games == 4
    assert next_year.completed_seasons[0].stats == completed.season_stats
    assert next_year.scores.contact == pytest.approx(completed.scores.contact + 0.10)
    assert next_year.scores.power == pytest.approx(completed.scores.power + 0.08)

    same = simulate_season(_career(season_games=4))
    assert same == next_year


def test_development_is_score_authoritative_costed_and_capped() -> None:
    power = replace(_career(BatterArchetype.POWER), development_points=24)
    assert purchase_cost(power, BatterSkill.POWER) == 1
    after = spend_development_points(power, BatterSkill.POWER, 4)
    assert after.scores.power == pytest.approx(0.8)
    assert after.ratings.power > power.ratings.power
    assert after.season_purchases == 4
    assert after.season_skill_purchases[1] == 4
    with pytest.raises(ValueError, match="ability purchase cap"):
        spend_development_points(after, BatterSkill.POWER)

    high = replace(
        power,
        scores=replace(power.scores, power=4.0),
        origin=replace(power.origin, starting_scores=replace(power.scores, power=4.0)),
    )
    assert purchase_cost(high, BatterSkill.POWER) > purchase_cost(power, BatterSkill.POWER)


def test_development_rejects_invalid_or_unavailable_points() -> None:
    state = replace(_career(), development_points=0)
    with pytest.raises(ValueError, match="positive"):
        spend_development_points(state, BatterSkill.CONTACT, 0)
    with pytest.raises(ValueError, match="insufficient"):
        spend_development_points(state, BatterSkill.CONTACT)


def test_development_enforces_season_ability_potential_and_bank_caps() -> None:
    state = replace(_career(BatterArchetype.POWER), development_points=24)
    state = spend_development_points(state, BatterSkill.POWER, 4)
    state = spend_development_points(state, BatterSkill.CONTACT, 4)
    state = spend_development_points(state, BatterSkill.EYE, 4)
    with pytest.raises(ValueError, match="season purchase cap"):
        spend_development_points(state, BatterSkill.POWER)

    capped = replace(
        _career(BatterArchetype.POWER),
        development_points=24,
        scores=replace(
            _career(BatterArchetype.POWER).scores,
            power=_career(BatterArchetype.POWER).origin.potential_scores.power,
        ),
    )
    with pytest.raises(ValueError, match="potential"):
        spend_development_points(capped, BatterSkill.POWER)
    with pytest.raises(ValueError, match="bank"):
        replace(_career(), development_points=25)


def test_speed_proxy_is_read_only_and_does_not_change_pa_outcomes() -> None:
    base = _career(seed=999)
    fast = replace(base, scores=replace(base.scores, speed_proxy=5.0))
    assert simulate_games(base, 5).season_stats == simulate_games(fast, 5).season_stats
    with pytest.raises(ValueError, match="read-only"):
        spend_development_points(replace(base, development_points=24), BatterSkill.SPEED_PROXY)


def test_xp_is_participation_only_not_outcome_quality() -> None:
    first = play_game(_career(seed=1), plate_appearances=6)
    second = play_game(_career(seed=999), plate_appearances=6)
    assert first.experience == first.season_stats.pa
    assert second.experience == second.season_stats.pa


def test_partial_game_is_replayable_and_blocks_training_and_season_advance() -> None:
    origin = replace(_career(), development_points=24)
    partial = next_pa(origin)
    assert partial.games_played == 0
    assert partial.experience == 1
    assert partial.active_game is not None
    assert len(partial.active_game.career_outcomes) == 1
    assert partial.active_game.game_state.plate_appearances == 1
    assert replay_career(_career(), partial.events) == replace(
        partial, development_points=0
    )
    with pytest.raises(ValueError, match="active game"):
        spend_development_points(partial, BatterSkill.CONTACT)
    with pytest.raises(ValueError, match="active game"):
        advance_season(partial)

    completed = play_game(partial)
    assert completed.games_played == 1
    assert completed.experience > 1
    assert completed.experience == completed.season_stats.pa
    assert completed.active_game is None


def test_pa_reward_conserves_expired_points_at_bank_cap() -> None:
    state = replace(_career(), experience=59, development_points=24)
    progressed = next_pa(state)
    assert progressed.experience == 60
    assert progressed.development_points == 24
    assert progressed.expired_development_points == 1


def test_week_counts_a_partial_game_and_never_crosses_season() -> None:
    partial = next_pa(_career(season_games=4))
    completed = simulate_week(partial, games=6)
    assert completed.games_played == 4
    assert completed.active_game is None
    assert completed.season_year == 2026
    with pytest.raises(ValueError, match="complete"):
        simulate_week(completed)


def test_next_event_stops_at_dp_game_or_completed_season_boundary() -> None:
    threshold = simulate_to_next_event(replace(_career(season_games=2), experience=59))
    assert threshold.active_game is not None
    assert threshold.experience == 60
    assert threshold.development_points == 1

    complete = simulate_to_next_event(_career(season_games=1))
    assert complete.games_played == 1
    assert complete.active_game is None
    advanced = simulate_to_next_event(complete)
    assert advanced.season_year == 2027
    assert advanced.games_played == 0


def test_career_retires_after_twenty_completed_seasons() -> None:
    state = _career(season_games=1)
    for _ in range(20):
        state = simulate_season(state, plate_appearances=1)
    assert state.retired
    assert state.season_year == 2045
    assert state.age == 37
    assert state.games_played == 1
    assert state.season_stats.games == 1
    assert state.completed_seasons[-1].season_year == 2045
    with pytest.raises(ValueError, match="retired"):
        play_game(state)
    with pytest.raises(ValueError, match="retired"):
        spend_development_points(
            replace(state, development_points=24), BatterSkill.CONTACT
        )


@pytest.mark.parametrize(
    ("archetype", "skill", "expected_score", "expected_display"),
    [
        (BatterArchetype.CONTACT, BatterSkill.CONTACT, 4.65, 98),
        (BatterArchetype.POWER, BatterSkill.POWER, 4.40, 97),
        (BatterArchetype.PATIENT, BatterSkill.EYE, 4.74, 99),
    ],
)
def test_twenty_season_primary_training_goldens(
    archetype: BatterArchetype,
    skill: BatterSkill,
    expected_score: float,
    expected_display: int,
) -> None:
    # This is a progression golden, not a game-engine load test. Credit the documented
    # 480-PA participation fixture directly so adding a full nine-inning M3 game to Career
    # does not make this test simulate tens of thousands of unrelated lineup appearances.
    state = _career(archetype, season_games=12)
    for _ in range(20):
        prior_experience = state.experience
        next_experience = prior_experience + 480
        crossed = next_experience // 60 - prior_experience // 60
        awarded = min(crossed, 24 - state.development_points)
        completed_fixture = BattingStats(games=state.origin.season_games)
        state = replace(
            state,
            games_played=state.origin.season_games,
            experience=next_experience,
            development_points=state.development_points + awarded,
            expired_development_points=(
                state.expired_development_points + crossed - awarded
            ),
            season_stats=completed_fixture,
            career_stats=state.career_stats + completed_fixture,
        )
        for _ in range(4):
            if state.development_points >= purchase_cost(state, skill):
                state = spend_development_points(state, skill)
        state = advance_season(state)
    assert state.scores.get(skill) == pytest.approx(expected_score, abs=1e-9)
    assert state.ratings.display[list(BatterSkill).index(skill)] == expected_display
    assert state.retired


def test_event_stream_replays_games_training_and_seasons_exactly() -> None:
    origin = _career(season_games=15)
    state = simulate_games(origin, 15, plate_appearances=6)
    assert state.development_points > 0
    state = spend_development_points(state, BatterSkill.EYE)
    state = simulate_to_season_end(state)
    state = advance_season(state)
    state = simulate_games(state, 3)
    assert replay_career(origin, state.events) == state

