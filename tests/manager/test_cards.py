from __future__ import annotations

from dataclasses import replace

import pytest

from baseball_sim.manager import (
    TIER_POLICY_VERSION,
    AbilityRating,
    BatSide,
    CardCatalog,
    CardKind,
    PitcherRole,
    PlayerSeasonCard,
    ThrowSide,
    Tier,
    impact,
)
from baseball_sim.ratings.mapping import score_to_rating


def _ability(score: float) -> AbilityRating:
    return AbilityRating(score, score_to_rating(score))


def _batter(index: int, score: float, *, year: int = 2025) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        card_id=f"b-{index}-{year}",
        player_id=f"b-{index}",
        player_name=f"Batter {index}",
        season_year=year,
        team="T",
        kind=CardKind.BATTER,
        model_version="batter-v1",
        mapping_version="B_QuadraticTanh",
        profile_positions=("CF",),
        bats=BatSide.LEFT,
        throws=ThrowSide.RIGHT,
        abilities={
            "Contact": _ability(score),
            "Power": _ability(score),
            "Eye": _ability(score),
            "SpeedProxy": _ability(0.0),
        },
        incomplete_season=year == 2026,
    )


def _pitcher(index: int, score: float) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        card_id=f"p-{index}",
        player_id=f"p-{index}",
        player_name=f"Pitcher {index}",
        season_year=2025,
        team="T",
        kind=CardKind.PITCHER,
        model_version="pitcher-v1",
        mapping_version="B_QuadraticTanh",
        profile_positions=("P",),
        bats=BatSide.RIGHT,
        throws=ThrowSide.RIGHT,
        abilities={
            "Stuff": _ability(score),
            "Control": _ability(score),
            "HRSuppression": _ability(score),
            "Stamina": _ability(2.0),
        },
        pitcher_role=PitcherRole.STARTER,
    )


def test_ability_requires_existing_score_to_raw_mapping() -> None:
    with pytest.raises(ValueError, match="does not match"):
        AbilityRating(1.0, 65.0)


def test_analytic_impact_uses_raw_matchup_and_ignores_stamina_for_pitchers() -> None:
    neutral_batter = _batter(1, 0.0)
    strong_batter = _batter(2, 2.0)
    neutral_pitcher = _pitcher(1, 0.0)
    strong_pitcher = _pitcher(2, 2.0)
    assert impact(strong_batter) > impact(neutral_batter)
    assert impact(strong_pitcher) > impact(neutral_pitcher)

    stamina_only = replace(
        neutral_pitcher,
        card_id="p-stamina",
        player_id="p-stamina",
        abilities={**neutral_pitcher.abilities, "Stamina": _ability(5.0)},
    )
    assert impact(stamina_only) == pytest.approx(impact(neutral_pitcher))


def test_completed_pool_percentile_tiers_and_fixed_costs() -> None:
    cards = [_batter(index, -2.0 + index * 0.2) for index in range(20)]
    catalog = CardCatalog("snapshot-v1", cards)
    tiers = [entry.tier for entry in catalog.entries(competitive_only=True)]
    assert tiers.count(Tier.N) == 8
    assert tiers.count(Tier.R) == 7
    assert tiers.count(Tier.SR) == 4
    assert tiers.count(Tier.SSR) == 1
    assert {
        entry.tier: entry.cost for entry in catalog.entries(competitive_only=True)
    } == {Tier.N: 1, Tier.R: 3, Tier.SR: 6, Tier.SSR: 10}
    assert all(entry.policy_version == TIER_POLICY_VERSION for entry in catalog.entries())


def test_2026_card_is_visible_but_has_no_competitive_tier_or_cost() -> None:
    completed = _batter(1, 0.0)
    incomplete = _batter(2, 5.0, year=2026)
    catalog = CardCatalog("snapshot-v1", [completed, incomplete])
    entry = catalog.get(incomplete.card_id)
    assert not entry.card.competitive
    assert entry.percentile is entry.tier is entry.cost is None
    assert [item.card.card_id for item in catalog.entries(competitive_only=True)] == [
        completed.card_id
    ]


def test_exact_profile_position_derives_of_family_and_pitcher_batter_dh() -> None:
    outfielder = _batter(1, 0.0)
    assert outfielder.profile_positions == ("CF",)
    assert outfielder.eligible_positions == frozenset({"CF", "OF"})
    pitcher_batter = replace(outfielder, profile_positions=("P",))
    assert pitcher_batter.profile_positions == ("P",)
    assert pitcher_batter.eligible_positions == frozenset({"P", "DH"})


def test_artifact_contract_rejects_missing_abilities_and_bad_incomplete_flag() -> None:
    with pytest.raises(ValueError, match="ability contract"):
        PlayerSeasonCard(
            card_id="bad",
            player_id="bad",
            player_name="Bad",
            season_year=2025,
            team="T",
            kind=CardKind.BATTER,
            model_version="v1",
            mapping_version="map",
            profile_positions=("CF",),
            bats=BatSide.LEFT,
            throws=ThrowSide.RIGHT,
            abilities={"Contact": _ability(0.0)},
        )
    with pytest.raises(ValueError, match="2026"):
        replace(_batter(1, 0.0), season_year=2026)
