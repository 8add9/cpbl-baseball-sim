from __future__ import annotations

import pandas as pd
import pytest

from baseball_sim.ratings.export import build_batter_snapshot, build_pitcher_snapshot


def _ability_rows(abilities: tuple[str, ...], pitcher: bool = False) -> pd.DataFrame:
    rows = []
    for player_id, year, incomplete in [(1, 2025, False), (2, 2026, True)]:
        for index, ability in enumerate(abilities):
            row = {
                "PlayerID": player_id,
                "PlayerName": f"Player {player_id}",
                "SeasonYear": year,
                "Team": "Test Team",
                "PA": 500,
                "Ability": ability,
                "CompositeScore": float(index - 1),
                "Eligible": True,
                "Confidence": "Qualified",
                "IncompleteSeason": incomplete,
                "AsOfDate": "2026-08-11",
            }
            if pitcher:
                row.update({"Role": "SP", "G": 25, "GS": 25, "IP": 150.0, "BF": 620})
            rows.append(row)
    return pd.DataFrame(rows)


def test_build_batter_snapshot_has_unique_versioned_cards() -> None:
    output = build_batter_snapshot(_ability_rows(("Contact", "Power", "Eye", "SpeedProxy")))
    assert len(output) == 2
    assert not output.duplicated(["PlayerID", "SeasonYear", "ModelVersion"]).any()
    assert output.loc[output.SeasonYear.eq(2026), "IncompleteSeason"].all()
    assert output.filter(like="RatingRaw").notna().all().all()


def test_build_pitcher_snapshot_excludes_overall_and_preserves_role() -> None:
    output = build_pitcher_snapshot(
        _ability_rows(("Stuff", "Control", "HRSuppression", "Stamina"), pitcher=True)
    )
    assert len(output) == 2
    assert set(output.Role) == {"SP"}
    assert not any("Overall" in column for column in output.columns)


def test_incomplete_ability_set_is_rejected() -> None:
    source = _ability_rows(("Contact", "Power", "Eye", "SpeedProxy"))
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        build_batter_snapshot(source.iloc[:-1])
