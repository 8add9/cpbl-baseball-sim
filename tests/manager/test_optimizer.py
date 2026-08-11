from __future__ import annotations

from pathlib import Path

import pytest

from baseball_sim.manager.loader import load_card_catalog
from baseball_sim.manager.optimizer import RosterStrategy, build_optimized_roster
from baseball_sim.manager.roster import RosterRules, evaluate_roster

ARTIFACT_ROOT = Path("artifacts/generated/ratings")


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for optimizer integration",
)
@pytest.mark.parametrize("strategy", list(RosterStrategy))
def test_real_catalog_builds_deterministic_legal_strategy_rosters(
    strategy: RosterStrategy,
) -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    first = build_optimized_roster(catalog, strategy)
    assert evaluate_roster(catalog, first.selection).legal
    assert first.total_cost <= 70
    assert len(first.lineup) == 9
    if strategy is RosterStrategy.BALANCED:
        assert first == build_optimized_roster(catalog, strategy)


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for optimizer integration",
)
def test_real_catalog_can_build_zero_ssr_non_all_star_roster() -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    rules = RosterRules(max_ssr=0, max_sr=3)
    result = build_optimized_roster(catalog, RosterStrategy.BALANCED, rules)
    legality = evaluate_roster(catalog, result.selection, rules)
    assert legality.legal
    assert legality.ssr_count == 0
    assert legality.sr_count <= 3


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for optimizer integration",
)
def test_real_catalog_strategies_allocate_budget_in_different_directions() -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    rosters = {
        strategy: build_optimized_roster(catalog, strategy)
        for strategy in RosterStrategy
    }

    def average_impact(strategy: RosterStrategy, *, batters: bool) -> float:
        selection = rosters[strategy].selection
        card_ids = (
            selection.batter_card_ids
            if batters
            else selection.rotation_card_ids + selection.bullpen_card_ids
        )
        return sum(catalog.get(card_id).impact for card_id in card_ids) / len(card_ids)

    assert (
        average_impact(RosterStrategy.OFFENSE, batters=True)
        > average_impact(RosterStrategy.BALANCED, batters=True)
        > average_impact(RosterStrategy.PITCHING, batters=True)
    )
    assert (
        average_impact(RosterStrategy.PITCHING, batters=False)
        > average_impact(RosterStrategy.BALANCED, batters=False)
        > average_impact(RosterStrategy.OFFENSE, batters=False)
    )
    card_sets = {
        frozenset(roster.selection.all_card_ids) for roster in rosters.values()
    }
    assert len(card_sets) == len(RosterStrategy)


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for optimizer integration",
)
def test_real_catalog_builds_six_disjoint_team_rosters() -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    used: set[str] = set()
    for index in range(6):
        strategy = list(RosterStrategy)[index % len(RosterStrategy)]
        result = build_optimized_roster(
            catalog, strategy, excluded_card_ids=used, beam_width=150
        )
        assert used.isdisjoint(result.selection.all_card_ids)
        used.update(result.selection.all_card_ids)
    assert len(used) == 132


def test_optimizer_rejects_invalid_search_contract() -> None:
    with pytest.raises(ValueError, match="beam_width"):
        build_optimized_roster(None, beam_width=0)  # type: ignore[arg-type]
