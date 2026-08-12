from __future__ import annotations

import pytest

from baseball_sim.manager.franchise import advance_to_next_season, create_franchise

TEAMS = ("A", "B", "C", "D", "E", "F")


def _entitlements(franchise):
    return {item.team_id: item for item in franchise.entitlements}


def _bonus(franchise, team_id):
    item = _entitlements(franchise)[team_id]
    return item.ssr_cap_bonus, item.cost_budget_bonus


def test_next_season_is_deterministic_and_champion_reward_accumulates() -> None:
    initial = create_franchise(TEAMS, 2026)
    first = advance_to_next_season(initial, TEAMS)
    assert first == advance_to_next_season(initial, TEAMS)
    assert first.active_season_year == 2027
    assert len(first.reward_grants) == 1
    assert _bonus(first, "A") == (1, 5)
    second = advance_to_next_season(first, TEAMS)
    assert _bonus(second, "A") == (2, 10)


def test_repeat_last_reward_is_a_ledger_grant_and_cumulative_entitlement() -> None:
    first = advance_to_next_season(create_franchise(TEAMS, 2026), TEAMS)
    second = advance_to_next_season(first, ("B", "A", "C", "D", "E", "F"))
    assert len(second.reward_grants) == 3
    catchup = [grant for grant in second.reward_grants if grant.reason == "consecutive-last-place"]
    assert len(catchup) == 1 and catchup[0].team_id == "F"
    assert _bonus(second, "F") == (2, 10)
    assert _bonus(second, "B") == (1, 5)


def test_changed_last_place_gets_no_grant_and_invalid_team_set_fails_closed() -> None:
    first = advance_to_next_season(create_franchise(TEAMS, 2026), TEAMS)
    changed = advance_to_next_season(first, ("A", "B", "C", "D", "F", "E"))
    assert not any(grant.team_id == "E" for grant in changed.reward_grants)
    with pytest.raises(ValueError, match="match"):
        advance_to_next_season(first, ("A", "B", "C", "D", "E", "X"))
