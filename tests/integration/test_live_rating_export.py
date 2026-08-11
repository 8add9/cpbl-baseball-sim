from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from dotenv import dotenv_values

from baseball_sim.ratings.export import export_snapshots

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("BASEBALL_DATA_INTEGRATION") != "1",
    reason="set BASEBALL_DATA_INTEGRATION=1 to test the live read-only source",
)
def test_live_rating_snapshot_contract(tmp_path: Path) -> None:
    data_dir = Path(os.environ["BASEBALL_DATA_DIR"])
    config = dict(dotenv_values(os.environ["BASEBALL_DATA_ENV"]))
    manifest = export_snapshots(data_dir, tmp_path, config)
    assert manifest["outputs"]["batter"]["rows"] == 3035
    assert manifest["outputs"]["pitcher"]["rows"] == 2125
    assert manifest["outputs"]["player_profiles"]["rows"] == 2138
    assert manifest["source_database"]["identity"] == "baseball_game_reader"
    assert manifest["invariants"]["overall_included"] is False

    batter = pd.read_csv(tmp_path / "batter_season_ratings.csv")
    pitcher = pd.read_csv(tmp_path / "pitcher_season_ratings.csv")
    profiles = pd.read_csv(tmp_path / "player_profiles.csv")
    slugger = batter[(batter.PlayerName == "高國輝") & (batter.SeasonYear == 2014)].iloc[0]
    ace = pitcher[(pitcher.PlayerName == "賈西") & (pitcher.SeasonYear == 1998)].iloc[0]
    assert slugger.PowerRatingRaw == pytest.approx(105.625370, abs=1e-6)
    assert ace.StuffRatingRaw == pytest.approx(98.048712, abs=1e-6)
    assert batter.loc[batter.SeasonYear.eq(2026), "IncompleteSeason"].all()
    assert pitcher.loc[pitcher.SeasonYear.eq(2026), "IncompleteSeason"].all()
    assert not any("Overall" in column for column in pitcher.columns)
    assert profiles.PlayerID.is_unique
    valid_positions = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "P"}
    assert set(profiles.ProfilePosition) <= valid_positions
