from __future__ import annotations

import pytest

from baseball_sim.manager.player_stats import (
    BatterStatLine,
    PitcherStatLine,
    PlayerSeasonStat,
    merge_player_season_stats,
)


def test_batter_stats_aggregate_and_compute_rate_stats() -> None:
    game = BatterStatLine(
        games=1, pa=5, ab=4, hits=2, doubles=1, home_runs=1,
        walks=1, strikeouts=1,
    )
    season = game + game
    assert season.games == 2 and season.home_runs == 2
    assert season.total_bases == 12
    assert season.avg == 0.5
    assert season.obp == 0.6
    assert season.slg == 1.5
    assert season.ops == 2.1


def test_pitcher_outs_are_authoritative_and_ledger_order_is_deterministic() -> None:
    line = PitcherStatLine(
        games=1, games_started=1, outs_recorded=20, batters_faced=27,
        hits=5, home_runs=1, walks=2, strikeouts=8, runs=2,
    )
    assert line.innings_pitched == "6.2"
    assert line.runs_allowed_per_nine == 2.7
    assert line.whip == 1.05
    pitcher = PlayerSeasonStat("z", 2026, pitcher=line, team_id="team-2")
    batter = PlayerSeasonStat(
        "a", 2026, batter=BatterStatLine(games=1), team_id="team-1"
    )
    ledger = merge_player_season_stats((), pitcher)
    ledger = merge_player_season_stats(ledger, batter)
    ledger = merge_player_season_stats(ledger, pitcher)
    assert tuple(item.card_id for item in ledger) == ("a", "z")
    assert ledger[1].pitcher is not None and ledger[1].pitcher.games == 2


def test_same_card_on_two_teams_keeps_separate_stat_lines() -> None:
    first = PlayerSeasonStat(
        "card", 2026, batter=BatterStatLine(games=1, pa=1, ab=1), team_id="team-1"
    )
    second = PlayerSeasonStat(
        "card", 2026, batter=BatterStatLine(games=1, pa=1, ab=1), team_id="team-2"
    )
    ledger = merge_player_season_stats(merge_player_season_stats((), first), second)
    assert [(item.team_id, item.card_id) for item in ledger] == [
        ("team-1", "card"),
        ("team-2", "card"),
    ]


def test_stats_reject_impossible_lines_and_cross_season_merges() -> None:
    with pytest.raises(ValueError, match="hit totals"):
        BatterStatLine(pa=1, ab=1, hits=1, doubles=2)
    current = (PlayerSeasonStat("a", 2026, batter=BatterStatLine()),)
    with pytest.raises(ValueError, match="across seasons"):
        merge_player_season_stats(
            current, PlayerSeasonStat("a", 2027, batter=BatterStatLine())
        )
