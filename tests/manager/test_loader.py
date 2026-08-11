from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import pytest

from baseball_sim.manager import TIER_POLICY_VERSION, CardKind, Tier, load_card_catalog
from baseball_sim.ratings.mapping import score_to_rating


def _write_csv(path: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {
        "path": path.name,
        "rows": len(rows),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _rating_row(kind: str) -> dict[str, object]:
    common: dict[str, object] = {
        "PlayerID": "1" if kind == "batter" else "2",
        "PlayerName": "Batter" if kind == "batter" else "Pitcher",
        "SeasonYear": 2025,
        "Team": "T",
        "ModelVersion": f"{kind}-v1",
        "MappingVersion": "map-v1",
        "IncompleteSeason": "False",
    }
    names = (
        ("Contact", "Power", "Eye", "SpeedProxy")
        if kind == "batter"
        else ("Stuff", "Control", "HRSuppression", "Stamina")
    )
    for name in names:
        common[f"{name}Score"] = 0.0
        common[f"{name}RatingRaw"] = score_to_rating(0.0)
    if kind == "pitcher":
        common["Role"] = "SP"
    return common


def _artifact(root: Path) -> None:
    batter = _write_csv(root / "batter_season_ratings.csv", [_rating_row("batter")])
    pitcher = _write_csv(root / "pitcher_season_ratings.csv", [_rating_row("pitcher")])
    profiles = _write_csv(
        root / "player_profiles.csv",
        [
            {
                "PlayerID": "1",
                "PlayerName": "Batter",
                "ProfileVersion": "profile-v1",
                "ProfilePosition": "CF",
                "Bats": "L",
                "Throws": "R",
            },
            {
                "PlayerID": "2",
                "PlayerName": "Pitcher",
                "ProfileVersion": "profile-v1",
                "ProfilePosition": "P",
                "Bats": "R",
                "Throws": "R",
            },
        ],
    )
    profiles["version"] = "profile-v1"
    manifest = {
        "schema_version": "rating-snapshot-v0.2",
        "mapping_version": "map-v1",
        "models": {"batter": "batter-v1", "pitcher": "pitcher-v1"},
        "outputs": {
            "batter": batter,
            "pitcher": pitcher,
            "player_profiles": profiles,
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )


def test_three_csv_manifest_loader_builds_canonical_cards_and_pins_hash(
    tmp_path: Path,
) -> None:
    _artifact(tmp_path)
    catalog = load_card_catalog(tmp_path)
    assert len(catalog.entries()) == 2
    batter = next(entry for entry in catalog.entries() if entry.card.kind == "batter")
    assert batter.card.card_id == "batter:1:2025:batter-v1:map-v1"
    assert batter.card.profile_positions == ("CF",)
    assert len(catalog.fingerprint) == 64


def test_loader_fails_closed_on_fingerprint_mismatch(tmp_path: Path) -> None:
    _artifact(tmp_path)
    with (tmp_path / "batter_season_ratings.csv").open("a", encoding="utf-8") as stream:
        stream.write("tampered")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_card_catalog(tmp_path)


def test_local_generated_v02_artifact_loads_when_available() -> None:
    root = Path("artifacts/generated/ratings")
    if not (root / "manifest.json").exists():
        pytest.skip("local ignored rating artifacts are unavailable")
    catalog = load_card_catalog(root)
    assert len(catalog.entries()) == 5_160
    competitive = catalog.entries(competitive_only=True)
    assert len(competitive) == 5_001
    incomplete = [entry for entry in catalog.entries() if not entry.card.competitive]
    assert len(incomplete) == 159
    assert all(entry.tier is entry.cost is entry.percentile is None for entry in incomplete)
    expected = {
        CardKind.BATTER: {Tier.N: 1176, Tier.R: 1029, Tier.SR: 588, Tier.SSR: 147},
        CardKind.PITCHER: {Tier.N: 824, Tier.R: 721, Tier.SR: 412, Tier.SSR: 104},
    }
    for kind, tier_counts in expected.items():
        pool = [entry for entry in competitive if entry.card.kind is kind]
        assert {tier: sum(entry.tier is tier for entry in pool) for tier in Tier} == tier_counts
    assert all(entry.policy_version == TIER_POLICY_VERSION for entry in catalog.entries())
    assert all(math.isfinite(entry.impact) for entry in catalog.entries())
