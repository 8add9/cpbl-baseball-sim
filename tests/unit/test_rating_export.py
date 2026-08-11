from __future__ import annotations

import pandas as pd
import pytest

from baseball_sim.ratings.export import (
    build_batter_snapshot,
    build_pitcher_snapshot,
    build_player_profiles,
)


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


def test_player_profiles_normalize_position_and_handedness() -> None:
    source = pd.DataFrame(
        [
            {
                "PlayerID": 2,
                "PlayerName": "Pitcher",
                "Position": "投手",
                "Bats": "左",
                "Throws": "右",
            },
            {
                "PlayerID": 1,
                "PlayerName": "Catcher",
                "Position": "捕手",
                "Bats": "左右",
                "Throws": "右",
            },
        ]
    )
    profiles = build_player_profiles(source)
    assert profiles.PlayerID.tolist() == [1, 2]
    assert profiles.ProfilePosition.tolist() == ["C", "P"]
    assert profiles.Bats.tolist() == ["S", "L"]
    assert profiles.Throws.tolist() == ["R", "R"]
    assert set(profiles.ProfileVersion) == {"player-profile-v0.1"}


def test_player_profiles_reject_unknown_or_duplicate_identity() -> None:
    source = pd.DataFrame(
        [
            {"PlayerID": 1, "PlayerName": "A", "Position": "捕手", "Bats": "右", "Throws": "右"},
            {"PlayerID": 1, "PlayerName": "B", "Position": "未知", "Bats": "右", "Throws": "右"},
        ]
    )
    with pytest.raises(ValueError, match="unique"):
        build_player_profiles(source)
    with pytest.raises(ValueError, match="unsupported"):
        build_player_profiles(source.iloc[[1]].assign(PlayerID=2))
