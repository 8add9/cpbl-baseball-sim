from __future__ import annotations

from dataclasses import replace

import pytest

from baseball_sim.manager.cards import (
    AbilityRating,
    BatSide,
    CardCatalog,
    CardKind,
    PitcherRole,
    PlayerSeasonCard,
    ThrowSide,
)
from baseball_sim.manager.usage import (
    PitcherAvailability,
    PitcherUsageEvent,
    apply_pitcher_usage,
    available_bullpen,
    create_pitcher_availability,
    eligible_starters,
    replay_pitcher_usage,
    select_next_starter,
)
from baseball_sim.ratings.mapping import score_to_rating


def _ability(score: float = 0.0) -> AbilityRating:
    return AbilityRating(score, score_to_rating(score))


def _pitcher(card_id: str, role: PitcherRole) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        card_id=card_id,
        player_id=card_id,
        player_name=card_id,
        season_year=2025,
        team="T",
        kind=CardKind.PITCHER,
        model_version="p-v1",
        mapping_version="map-v1",
        profile_positions=("P",),
        bats=BatSide.RIGHT,
        throws=ThrowSide.RIGHT,
        abilities={
            name: _ability()
            for name in ("Stuff", "Control", "HRSuppression", "Stamina")
        },
        pitcher_role=role,
    )


def _fixture() -> tuple[PitcherAvailability, tuple[str, ...], tuple[str, ...]]:
    rotation = ("sp-z", "sp-a", "sp-m", "sp-b")
    bullpen = ("rp-z", "sw-b", "rp-a", "sw-a", "rp-m")
    cards = [*(_pitcher(card_id, PitcherRole.STARTER) for card_id in rotation)]
    cards.extend(
        _pitcher(
            card_id,
            PitcherRole.RELIEVER if card_id.startswith("rp") else PitcherRole.SWINGMAN,
        )
        for card_id in bullpen
    )
    # Extra competitive cards keep catalog percentile construction representative while
    # remaining outside this team's usage state.
    cards.extend(_pitcher(f"reserve-{index}", PitcherRole.RELIEVER) for index in range(10))
    cards.append(_pitcher("reserve-sp", PitcherRole.STARTER))
    catalog = CardCatalog("snapshot-v1", cards)
    return create_pitcher_availability(catalog, rotation, bullpen), rotation, bullpen


def _event(
    state: PitcherAvailability, starter: str, *relievers: str
) -> PitcherUsageEvent:
    return PitcherUsageEvent(
        state.next_game_number, starter, (starter, *relievers)
    )


def test_initial_selection_follows_rotation_and_bullpen_uses_card_id_order() -> None:
    state, rotation, bullpen = _fixture()
    assert eligible_starters(state) == rotation
    assert select_next_starter(state) == rotation[0]
    assert available_bullpen(state) == tuple(sorted(bullpen))


def test_four_sp_rotation_requires_four_team_games_between_starts() -> None:
    state, rotation, _bullpen = _fixture()
    for starter in rotation:
        assert select_next_starter(state) == starter
        state = apply_pitcher_usage(state, _event(state, starter))
    assert state.team_games_played == 4
    assert select_next_starter(state) == rotation[0]
    state = apply_pitcher_usage(state, _event(state, rotation[0]))
    assert dict(state.last_start_games)[rotation[0]] == 5


def test_short_rest_start_is_rejected_without_mutating_state() -> None:
    state, rotation, _bullpen = _fixture()
    state = apply_pitcher_usage(state, _event(state, rotation[0]))
    before = state
    with pytest.raises(ValueError, match="rested four"):
        apply_pitcher_usage(state, _event(state, rotation[0]))
    assert state == before


def test_reliever_may_pitch_twice_then_must_rest_and_unused_resets_streak() -> None:
    state, rotation, bullpen = _fixture()
    reliever = bullpen[0]
    state = apply_pitcher_usage(state, _event(state, rotation[0], reliever))
    state = apply_pitcher_usage(state, _event(state, rotation[1], reliever))
    assert dict(state.relief_streaks)[reliever] == 2
    assert reliever not in available_bullpen(state)
    before = state
    with pytest.raises(ValueError, match="third consecutive"):
        apply_pitcher_usage(state, _event(state, rotation[2], reliever))
    assert state == before

    state = apply_pitcher_usage(state, _event(state, rotation[2]))
    assert dict(state.relief_streaks)[reliever] == 0
    assert reliever in available_bullpen(state)


def test_each_unused_reliever_resets_independently() -> None:
    state, rotation, bullpen = _fixture()
    first, second = bullpen[:2]
    state = apply_pitcher_usage(state, _event(state, rotation[0], first, second))
    state = apply_pitcher_usage(state, _event(state, rotation[1], first))
    streaks = dict(state.relief_streaks)
    assert streaks[first] == 2
    assert streaks[second] == 0


def test_role_and_roster_boundaries_fail_closed() -> None:
    state, rotation, bullpen = _fixture()
    with pytest.raises(ValueError, match="four-card SP rotation"):
        apply_pitcher_usage(state, _event(state, bullpen[0]))
    with pytest.raises(ValueError, match="RP or Swingman"):
        apply_pitcher_usage(state, _event(state, rotation[0], rotation[1]))
    with pytest.raises(ValueError, match="RP or Swingman"):
        apply_pitcher_usage(state, _event(state, rotation[0], "unknown"))


def test_event_validation_rejects_duplicates_missing_starter_and_out_of_order() -> None:
    state, rotation, bullpen = _fixture()
    with pytest.raises(ValueError, match="first"):
        PitcherUsageEvent(1, rotation[0], (bullpen[0], rotation[0]))
    with pytest.raises(ValueError, match="twice"):
        PitcherUsageEvent(1, rotation[0], (rotation[0], bullpen[0], bullpen[0]))
    with pytest.raises(ValueError, match="team-game order"):
        apply_pitcher_usage(
            state, PitcherUsageEvent(2, rotation[0], (rotation[0],))
        )


def test_factory_rejects_wrong_roles_unknown_cards_and_tracking_corruption() -> None:
    state, rotation, bullpen = _fixture()
    with pytest.raises(ValueError, match="SP role"):
        create_pitcher_availability(
            state.catalog, ("reserve-0", *rotation[1:]), bullpen
        )
    with pytest.raises(ValueError, match="RP or Swingman"):
        create_pitcher_availability(
            state.catalog, rotation, ("reserve-sp", *bullpen[1:])
        )
    with pytest.raises(ValueError, match="unknown rotation"):
        create_pitcher_availability(
            state.catalog, ("missing", *rotation[1:]), bullpen
        )
    with pytest.raises(ValueError, match="last-start tracking"):
        replace(state, last_start_games=state.last_start_games[:-1])
    with pytest.raises(ValueError, match="relief streak"):
        replace(
            state,
            relief_streaks=((bullpen[0], 3), *state.relief_streaks[1:]),
        )


def test_replay_is_immutable_and_identical_for_the_same_event_stream() -> None:
    initial, rotation, bullpen = _fixture()
    events = (
        PitcherUsageEvent(1, rotation[0], (rotation[0], bullpen[0], bullpen[1])),
        PitcherUsageEvent(2, rotation[1], (rotation[1], bullpen[0])),
        PitcherUsageEvent(3, rotation[2], (rotation[2], bullpen[1])),
        PitcherUsageEvent(4, rotation[3], (rotation[3],)),
        PitcherUsageEvent(5, rotation[0], (rotation[0], bullpen[0])),
    )
    first = replay_pitcher_usage(initial, events)
    second = replay_pitcher_usage(initial, events)
    assert first == second
    assert initial.team_games_played == 0
    assert dict(first.last_start_games)[rotation[0]] == 5
    assert dict(first.relief_streaks)[bullpen[0]] == 1
