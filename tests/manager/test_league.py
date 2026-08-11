from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from baseball_sim.manager.league import (
    ManagerTeamConfig,
    create_manager_league,
    simulate_league_games,
    simulate_manager_season,
)
from baseball_sim.manager.loader import load_card_catalog
from baseball_sim.manager.optimizer import RosterStrategy, build_optimized_roster

ARTIFACT_ROOT = Path("artifacts/generated/ratings")


def _league():
    catalog = load_card_catalog(ARTIFACT_ROOT)
    used: set[str] = set()
    teams = []
    for index in range(6):
        plan = build_optimized_roster(
            catalog,
            list(RosterStrategy)[index % len(RosterStrategy)],
            excluded_card_ids=used,
            beam_width=150,
        )
        used.update(plan.selection.all_card_ids)
        teams.append(ManagerTeamConfig(f"T{index + 1}", plan.selection, plan.lineup))
    return create_manager_league(catalog, tuple(teams), seed=20260812)


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for league integration",
)
def test_league_games_are_deterministic_and_update_usage_and_standings() -> None:
    initial = _league()
    first = simulate_league_games(initial, 12)
    second = simulate_league_games(_league(), 12)
    assert first.results == second.results
    assert first.standings == second.standings
    assert sum(row.wins for row in first.standings.rows) == 12
    assert sum(row.losses for row in first.standings.rows) == 12
    assert sum(row.runs_scored for row in first.standings.rows) == sum(
        row.runs_allowed for row in first.standings.rows
    )
    assert sum(team.pitcher_availability.team_games_played for team in first.teams) == 24


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for league integration",
)
def test_full_manager_season_completes_all_360_games() -> None:
    completed = simulate_manager_season(_league())
    assert completed.finished
    assert len(completed.results) == 360
    assert all(row.games == 120 for row in completed.standings.rows)
    assert sum(row.wins for row in completed.standings.rows) == 360
    assert sum(row.losses for row in completed.standings.rows) == 360


def test_league_simulation_rejects_nonpositive_batch() -> None:
    with pytest.raises(ValueError, match="positive"):
        simulate_league_games(None, 0)  # type: ignore[arg-type]


@pytest.mark.skipif(
    not (ARTIFACT_ROOT / "manifest.json").exists(),
    reason="generated rating artifact is required for league integration",
)
def test_league_creation_rejects_invalid_lineup_before_first_game() -> None:
    valid = _league()
    configs = tuple(team.config for team in valid.teams)
    invalid_lineup = (configs[0].lineup[0],) * 9
    invalid = replace(configs[0], lineup=invalid_lineup)
    with pytest.raises(ValueError):
        create_manager_league(valid.catalog, (invalid,) + configs[1:], seed=1)
