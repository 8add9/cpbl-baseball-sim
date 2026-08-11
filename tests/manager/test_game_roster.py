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
from baseball_sim.manager.game_roster import (
    LineupEntry,
    begin_batting_pa,
    begin_fielding_pa,
    change_pitcher,
    complete_batting_pa,
    complete_fielding_pa,
    create_team_game_roster,
    enable_emergency_extension,
    pinch_hit,
    pitcher_bf_capacity,
)
from baseball_sim.manager.roster import RosterSelection
from baseball_sim.ratings.mapping import rating_to_score, score_to_rating


def _ability(rating: float = 65.0) -> AbilityRating:
    score = rating_to_score(rating)
    return AbilityRating(score, score_to_rating(score))


def _batter(index: int, position: str) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        f"b{index}",
        f"b{index}",
        f"Batter {index}",
        2025,
        "T",
        CardKind.BATTER,
        "b-v1",
        "map-v1",
        (position,),
        BatSide.RIGHT,
        ThrowSide.RIGHT,
        {name: _ability() for name in ("Contact", "Power", "Eye", "SpeedProxy")},
    )


def _pitcher(index: int, role: PitcherRole, stamina: float = 65.0) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        f"p{index}",
        f"p{index}",
        f"Pitcher {index}",
        2025,
        "T",
        CardKind.PITCHER,
        "p-v1",
        "map-v1",
        ("P",),
        BatSide.RIGHT,
        ThrowSide.RIGHT,
        {
            "Stuff": _ability(),
            "Control": _ability(),
            "HRSuppression": _ability(),
            "Stamina": _ability(stamina),
        },
        pitcher_role=role,
    )


def _fixture():
    positions = ("C", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "LF", "CF", "RF")
    batters = [_batter(index, position) for index, position in enumerate(positions)]
    starters = [_pitcher(index, PitcherRole.STARTER) for index in range(4)]
    bullpen = [
        _pitcher(10 + index, PitcherRole.RELIEVER if index < 3 else PitcherRole.SWINGMAN)
        for index in range(5)
    ]
    reserves = [
        *[_batter(100 + index, "DH") for index in range(20)],
        *[_pitcher(100 + index, PitcherRole.RELIEVER) for index in range(20)],
    ]
    catalog = CardCatalog("snapshot-v1", [*batters, *starters, *bullpen, *reserves])
    roster = RosterSelection(
        tuple(card.card_id for card in batters),
        tuple(card.card_id for card in starters),
        tuple(card.card_id for card in bullpen),
    )
    starter_indexes = (0, 2, 3, 4, 5, 6, 7, 8, 9)
    starter_positions = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
    lineup = tuple(
        LineupEntry(batters[index].card_id, position)
        for index, position in zip(starter_indexes, starter_positions, strict=True)
    )
    return catalog, roster, lineup, batters, starters, bullpen


def test_builds_lineup9_bench4_rotation4_bullpen5_with_exact_positions() -> None:
    catalog, roster, lineup, _batters, starters, _bullpen = _fixture()
    state = create_team_game_roster(catalog, roster, lineup, starters[0].card_id)
    assert len(state.lineup) == 9
    assert len(state.bench_card_ids) == 4
    assert len(state.rotation_card_ids) == 4
    assert len(state.bullpen_card_ids) == 5
    assert state.current_batter.position == "C"


def test_exact_outfield_assignment_rejects_cf_card_in_lf_slot() -> None:
    catalog, roster, lineup, _batters, starters, _bullpen = _fixture()
    invalid = list(lineup)
    invalid[5] = LineupEntry(invalid[6].card_id, "LF")
    invalid[6] = LineupEntry(lineup[5].card_id, "CF")
    with pytest.raises(ValueError, match="exact ProfilePosition"):
        create_team_game_roster(catalog, roster, tuple(invalid), starters[0].card_id)


def test_pinch_hit_only_at_boundary_and_removed_batter_cannot_reenter() -> None:
    catalog, roster, lineup, batters, starters, _bullpen = _fixture()
    state = create_team_game_roster(catalog, roster, lineup, starters[0].card_id)
    incoming = batters[1].card_id
    state = pinch_hit(state, incoming)
    assert state.current_batter.card_id == incoming
    assert lineup[0].card_id in state.removed_batter_card_ids
    state = begin_batting_pa(state)
    with pytest.raises(ValueError, match="between plate appearances"):
        pinch_hit(state, batters[10].card_id)
    state = complete_batting_pa(state)
    with pytest.raises(ValueError, match="unused available bench"):
        pinch_hit(replace(state, current_batter_index=0), lineup[0].card_id)


def test_pitcher_change_is_boundary_only_and_used_pitcher_cannot_reenter() -> None:
    catalog, roster, lineup, _batters, starters, bullpen = _fixture()
    state = create_team_game_roster(catalog, roster, lineup, starters[0].card_id)
    state = begin_fielding_pa(state)
    with pytest.raises(ValueError, match="between plate appearances"):
        change_pitcher(state, bullpen[0].card_id)
    state = complete_fielding_pa(state)
    state = change_pitcher(state, bullpen[0].card_id)
    state = change_pitcher(state, bullpen[1].card_id)
    with pytest.raises(ValueError, match="re-enter"):
        change_pitcher(state, bullpen[0].card_id)


def test_cross_game_unavailable_bullpen_pitcher_cannot_enter() -> None:
    catalog, roster, lineup, _batters, starters, bullpen = _fixture()
    state = create_team_game_roster(
        catalog,
        roster,
        lineup,
        starters[0].card_id,
        (bullpen[0].card_id,),
    )
    with pytest.raises(ValueError, match="cross-game"):
        change_pitcher(state, bullpen[0].card_id)


@pytest.mark.parametrize(
    ("role", "rating", "expected"),
    [
        (PitcherRole.STARTER, 65.0, 24),
        (PitcherRole.STARTER, 67.0, 25),
        (PitcherRole.STARTER, 35.0, 18),
        (PitcherRole.STARTER, 105.0, 32),
        (PitcherRole.SWINGMAN, 67.5, 13),
        (PitcherRole.SWINGMAN, 35.0, 8),
        (PitcherRole.SWINGMAN, 105.0, 20),
        (PitcherRole.RELIEVER, 70.0, 6),
        (PitcherRole.RELIEVER, 35.0, 3),
        (PitcherRole.RELIEVER, 105.0, 8),
    ],
)
def test_stamina_raw_capacity_formula_and_clamps(
    role: PitcherRole, rating: float, expected: int
) -> None:
    assert pitcher_bf_capacity(_pitcher(999, role, rating)) == expected


def test_pitcher_at_cap_finishes_current_pa_then_must_change_before_next() -> None:
    catalog, roster, lineup, _batters, starters, bullpen = _fixture()
    state = create_team_game_roster(catalog, roster, lineup, starters[0].card_id)
    state = change_pitcher(state, bullpen[0].card_id)
    assert state.active_pitcher_capacity == 5
    for _ in range(5):
        state = complete_fielding_pa(begin_fielding_pa(state))
    assert state.active_pitcher_bf == 5
    assert state.pitcher_change_required
    with pytest.raises(ValueError, match="must be replaced"):
        begin_fielding_pa(state)
    replacement = change_pitcher(state, bullpen[1].card_id)
    assert not replacement.pitcher_change_required


def test_bullpen_exhaustion_can_extend_only_the_last_real_pitcher() -> None:
    catalog, roster, lineup, _batters, starters, bullpen = _fixture()
    state = create_team_game_roster(catalog, roster, lineup, starters[0].card_id)
    for pitcher in bullpen:
        state = change_pitcher(state, pitcher.card_id)
    for _ in range(state.active_pitcher_capacity):
        state = complete_fielding_pa(begin_fielding_pa(state))
    extended = enable_emergency_extension(state)
    assert extended.emergency_extension
    assert not extended.pitcher_change_required
    assert complete_fielding_pa(begin_fielding_pa(extended)).active_pitcher_bf > (
        extended.active_pitcher_capacity
    )
