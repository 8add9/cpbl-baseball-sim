from __future__ import annotations

from pathlib import Path

import pytest

from baseball_sim.manager.loader import load_card_catalog
from research.manager_balance_validation import (
    COMPARISONS,
    ChunkResult,
    _stable_seed,
    build_team_specs,
    simulate_comparisons,
    summarize_results,
    validate_run_arguments,
)

ARTIFACT_ROOT = Path("artifacts/generated/ratings")


def test_run_contract_requires_complete_pairs_and_positive_workers() -> None:
    for games, workers in ((1, 1), (3, 1), (2, 0)):
        with pytest.raises(ValueError):
            validate_run_arguments(games, workers)
    validate_run_arguments(2, 1)


def test_common_random_seed_is_stable_and_comparison_scoped() -> None:
    assert _stable_seed(7, "a", 2) == _stable_seed(7, "a", 2)
    assert _stable_seed(7, "a", 2) != _stable_seed(7, "b", 2)
    assert _stable_seed(7, "a", 2) != _stable_seed(7, "a", 3)


def test_summary_uses_pair_level_uncertainty_and_release_sample_gate() -> None:
    comparison = (COMPARISONS[0],)
    chunks = [ChunkResult(comparison[0].name, 2, 2, 1, 1, 8, 8, 1.0, 1.0)]
    row = summarize_results(comparison, chunks, games=4)[0]
    assert row["left_win_rate"] == 0.5
    assert row["left_wins_per_120"] == 60.0
    assert row["ci95_low"] < 0.5 < row["ci95_high"]
    assert not row["sample_gate_pass"]
    assert not row["release_gate_pass"]


def test_summary_applies_reference_and_mutual_balance_rules_separately() -> None:
    reference = (COMPARISONS[0],)
    reference_chunks = [
        ChunkResult(
            reference[0].name,
            10_000,
            11_000,
            5_500,
            5_500,
            0,
            0,
            5_500.0,
            4_000.0,
        )
    ]
    reference_row = summarize_results(reference, reference_chunks, games=20_000)[0]
    assert reference_row["left_win_rate"] == 0.55
    assert reference_row["metric_gate_pass"]

    mutual = (COMPARISONS[-1],)
    mutual_chunks = [
        ChunkResult(
            mutual[0].name,
            10_000,
            11_200,
            5_600,
            5_600,
            0,
            0,
            5_600.0,
            4_100.0,
        )
    ]
    mutual_row = summarize_results(mutual, mutual_chunks, games=20_000)[0]
    assert mutual_row["left_win_rate"] == 0.56
    assert not mutual_row["metric_gate_pass"]


@pytest.mark.integration
@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for balance integration",
)
def test_real_catalog_paired_simulation_is_reproducible_and_rosters_are_nonstar() -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    specs = build_team_specs(catalog)
    assert all(specs[name].ssr_count == 0 for name in ("balanced", "offense", "pitching"))
    assert all(specs[name].sr_count <= 3 for name in ("balanced", "offense", "pitching"))
    assert len({card for spec in specs.values() for card in spec.selection.all_card_ids}) == 88

    kwargs = {
        "artifact_root": ARTIFACT_ROOT,
        "games": 2,
        "workers": 1,
        "seed": 1234,
        "comparisons": (COMPARISONS[0],),
    }
    first = simulate_comparisons(catalog, specs, **kwargs)
    second = simulate_comparisons(catalog, specs, **kwargs)
    assert first == second
    assert first[0]["games"] == 2
    assert first[0]["pairs"] == 1
    assert first[0]["left_home_win_rate"] in {0.0, 1.0}
    assert first[0]["left_away_win_rate"] in {0.0, 1.0}
