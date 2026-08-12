from __future__ import annotations

from pathlib import Path

import pytest

from baseball_sim.manager.customization import (
    rename_team,
    roster_limits_for_name,
    set_rotation_plan,
    set_starting_lineup,
)
from baseball_sim.manager.game_roster import LineupEntry
from baseball_sim.manager.league import ManagerTeamConfig
from baseball_sim.manager.league_service import AI_CPBL_TEAM_NAMES
from baseball_sim.manager.loader import load_card_catalog
from baseball_sim.manager.optimizer import build_optimized_roster
from baseball_sim.manager.roster import RosterSelection

ARTIFACT_ROOT = Path("artifacts/generated/ratings")


def test_exact_8add9_name_has_unlimited_cost_and_ssr_caps() -> None:
    limits = roster_limits_for_name("8add9", cost_bonus=10, ssr_bonus=2)
    assert limits.unlimited
    assert limits.cost_limit is None
    assert limits.ssr_limit is None
    ordinary = roster_limits_for_name("8ADD9", cost_bonus=10, ssr_bonus=2)
    assert not ordinary.unlimited
    assert ordinary.cost_limit == 80
    assert ordinary.ssr_limit == 4


def test_display_name_is_independent_from_stable_team_id_and_ai_names_are_real() -> None:
    selection = RosterSelection(
        tuple(f"b{i}" for i in range(13)),
        tuple(f"s{i}" for i in range(4)),
        tuple(f"r{i}" for i in range(5)),
    )
    positions = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
    lineup = tuple(
        LineupEntry(f"b{i}", position) for i, position in enumerate(positions)
    )
    config = ManagerTeamConfig("stable-id", selection, lineup, name="Old")
    renamed = rename_team(config, "  我的球隊  ")
    assert renamed.team_id == "stable-id"
    assert renamed.name == "我的球隊"
    assert AI_CPBL_TEAM_NAMES == (
        "中信兄弟", "統一7-ELEVEn獅", "樂天桃猿", "味全龍", "富邦悍將", "台鋼雄鷹"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(), reason="rating artifact required"
)
def test_batting_order_and_four_sp_rotation_are_freely_reorderable() -> None:
    catalog = load_card_catalog(ARTIFACT_ROOT)
    plan = build_optimized_roster(catalog)
    batting_order = tuple(reversed(plan.lineup))
    assert set_starting_lineup(catalog, plan.selection, batting_order) == batting_order
    owned = plan.selection.rotation_card_ids
    rotation_plan = set_rotation_plan(plan.selection, (owned[0],) * 4)
    assert rotation_plan.starter_card_ids == (owned[0],) * 4
    assert len(set(plan.selection.rotation_card_ids)) == 4
    with pytest.raises(ValueError, match="owned"):
        set_rotation_plan(plan.selection, (owned[0], owned[1], owned[2], "not-owned"))
