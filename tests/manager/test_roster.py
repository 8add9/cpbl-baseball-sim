from __future__ import annotations

from dataclasses import replace

from baseball_sim.manager import (
    AbilityRating,
    BatSide,
    CardCatalog,
    CardKind,
    PitcherRole,
    PlayerSeasonCard,
    RosterRules,
    RosterSelection,
    ThrowSide,
    evaluate_roster,
)
from baseball_sim.ratings.mapping import score_to_rating


def _ability(score: float = 0.0) -> AbilityRating:
    return AbilityRating(score, score_to_rating(score))


def _batter(
    index: int, position: str, *, year: int = 2025, score: float = 0.0
) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        f"b{index}-{year}",
        f"b{index}",
        f"Batter {index}",
        year,
        "T",
        CardKind.BATTER,
        "b-v1",
        "map-v1",
        (position,),
        BatSide.RIGHT,
        ThrowSide.RIGHT,
        {
            name: _ability(score)
            for name in ("Contact", "Power", "Eye", "SpeedProxy")
        },
        year == 2026,
    )


def _pitcher(
    index: int, role: PitcherRole, *, score: float = 0.0
) -> PlayerSeasonCard:
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
            name: _ability(score)
            for name in ("Stuff", "Control", "HRSuppression", "Stamina")
        },
        pitcher_role=role,
    )


def _fixture() -> tuple[CardCatalog, RosterSelection, list[PlayerSeasonCard]]:
    positions = [
        "C", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "LF", "DH", "DH", "DH"
    ]
    batters = [
        _batter(index, position, score=-2.0)
        for index, position in enumerate(positions)
    ]
    starters = [_pitcher(index, PitcherRole.STARTER, score=-2.0) for index in range(4)]
    bullpen = [
        _pitcher(
            10 + index,
            PitcherRole.RELIEVER if index < 3 else PitcherRole.SWINGMAN,
            score=-2.0,
        )
        for index in range(5)
    ]
    cards = batters + starters + bullpen
    reserves = [
        *[_batter(200 + index, "DH", score=2.0) for index in range(10)],
        *[
            _pitcher(200 + index, PitcherRole.RELIEVER, score=2.0)
            for index in range(10)
        ],
    ]
    catalog = CardCatalog("snapshot-v1", [*cards, *reserves])
    selection = RosterSelection(
        tuple(card.card_id for card in batters),
        tuple(card.card_id for card in starters),
        tuple(card.card_id for card in bullpen),
    )
    return catalog, selection, cards


def test_researched_22_player_roster_is_legal_under_70_cost() -> None:
    catalog, selection, _cards = _fixture()
    result = evaluate_roster(catalog, selection)
    assert result.legal
    assert result.total_cost <= 70
    assert result.violations == ()


def test_budget_and_ssr_caps_are_reported_independently() -> None:
    catalog, selection, cards = _fixture()
    over_budget = evaluate_roster(catalog, selection, RosterRules(budget=21))
    assert any("exceeds budget" in item for item in over_budget.violations)

    high_abilities = {
        name: AbilityRating(5.0, score_to_rating(5.0))
        for name in ("Contact", "Power", "Eye", "SpeedProxy")
    }
    ssr = replace(
        cards[6], card_id="b-ssr", player_id="b-ssr", abilities=high_abilities
    )
    expanded = CardCatalog(
        "snapshot-v1", [*(entry.card for entry in catalog.entries()), ssr]
    )
    selected = replace(
        selection,
        batter_card_ids=(
            *selection.batter_card_ids[:6],
            ssr.card_id,
            *selection.batter_card_ids[7:],
        ),
    )
    capped = evaluate_roster(
        expanded, selected, RosterRules(budget=100, max_ssr=0)
    )
    assert capped.ssr_count == 1
    assert any("SSR count" in item for item in capped.violations)


def test_positions_are_distinct_assignments_not_one_utility_player() -> None:
    catalog, selection, _cards = _fixture()
    replacement = _batter(99, "DH")
    expanded = CardCatalog(
        "snapshot-v1", [*(entry.card for entry in catalog.entries()), replacement]
    )
    invalid = replace(
        selection,
        batter_card_ids=(replacement.card_id, *selection.batter_card_ids[1:]),
    )
    result = evaluate_roster(expanded, invalid)
    assert not result.legal
    assert any("2C" in violation for violation in result.violations)


def test_rotation_bullpen_roles_and_minimum_three_relief_pitchers() -> None:
    base_catalog, selection, _cards = _fixture()
    bad_starter = _pitcher(99, PitcherRole.RELIEVER)
    bad_swing = _pitcher(100, PitcherRole.SWINGMAN)
    catalog = CardCatalog(
        "snapshot-v1",
        [
            *(entry.card for entry in base_catalog.entries()),
            bad_starter,
            bad_swing,
        ],
    )
    wrong_rotation = replace(
        selection,
        rotation_card_ids=(bad_starter.card_id, *selection.rotation_card_ids[1:]),
    )
    assert any("SP role" in item for item in evaluate_roster(catalog, wrong_rotation).violations)
    too_few_rp = replace(
        selection,
        bullpen_card_ids=(bad_swing.card_id, *selection.bullpen_card_ids[1:]),
    )
    assert any("at least 3 RP" in item for item in evaluate_roster(catalog, too_few_rp).violations)


def test_one_season_per_player_and_2026_competitive_exclusion() -> None:
    base_catalog, selection, cards = _fixture()
    alternate = replace(
        cards[1],
        card_id="b0-2024",
        player_id=cards[0].player_id,
        season_year=2024,
    )
    future = _batter(98, "C", year=2026)
    catalog = CardCatalog(
        "snapshot-v1",
        [*(entry.card for entry in base_catalog.entries()), alternate, future],
    )
    duplicate_player = replace(
        selection,
        batter_card_ids=(
            selection.batter_card_ids[0],
            alternate.card_id,
            *selection.batter_card_ids[2:],
        ),
    )
    assert any(
        "one season card" in item
        for item in evaluate_roster(catalog, duplicate_player).violations
    )
    incomplete = replace(
        selection,
        batter_card_ids=(future.card_id, *selection.batter_card_ids[1:]),
    )
    assert any(
        "not eligible" in item for item in evaluate_roster(catalog, incomplete).violations
    )
