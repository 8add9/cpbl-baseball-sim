"""Application services over the single authoritative Manager league domain."""

from __future__ import annotations

from dataclasses import replace

from .cards import CardCatalog
from .league import (
    ManagerLeagueState,
    ManagerTeamConfig,
    create_manager_league,
    simulate_manager_season,
)
from .league import (
    simulate_next_league_game as simulate_next_domain_game,
)
from .optimizer import RosterStrategy, build_optimized_roster
from .roster import RosterSelection


def create_ai_league(catalog: CardCatalog, seed: int) -> ManagerLeagueState:
    """Create six legal, card-disjoint AI teams without duplicating league rules."""
    used: set[str] = set()
    configs: list[ManagerTeamConfig] = []
    strategies = tuple(RosterStrategy)
    for index in range(6):
        strategy = strategies[index % len(strategies)]
        optimized = build_optimized_roster(
            catalog,
            strategy,
            excluded_card_ids=used,
            beam_width=150,
        )
        if not used.isdisjoint(optimized.selection.all_card_ids):
            raise ValueError("AI roster optimizer reused a CardID across teams")
        used.update(optimized.selection.all_card_ids)
        configs.append(
            ManagerTeamConfig(
                team_id=f"team-{index + 1}",
                roster=optimized.selection,
                lineup=optimized.lineup,
                name=f"AI Team {index + 1}",
                strategy=strategy.value,
            )
        )
    if len(used) != 132:
        raise ValueError("six AI rosters must contain 132 unique CardIDs")
    return create_manager_league(catalog, tuple(configs), seed=seed)


def simulate_league_round(
    state: ManagerLeagueState, _catalog: CardCatalog
) -> ManagerLeagueState:
    """Complete the current three-game schedule round atomically."""
    scheduled = state.next_game
    if scheduled is None:
        raise ValueError("Manager season is complete")
    round_number = scheduled.round_number
    current = state
    while current.next_game is not None and current.next_game.round_number == round_number:
        current = simulate_next_domain_game(current)
    return current


def simulate_league_season(
    state: ManagerLeagueState, _catalog: CardCatalog
) -> ManagerLeagueState:
    return simulate_manager_season(state)


def simulate_next_league_game(
    state: ManagerLeagueState, _catalog: CardCatalog
) -> ManagerLeagueState:
    return simulate_next_domain_game(state)


def replace_team_card(
    state: ManagerLeagueState,
    catalog: CardCatalog,
    *,
    team_id: str,
    outgoing_card_id: str,
    incoming_card_id: str,
) -> ManagerLeagueState:
    """Replace one preseason card and revalidate the complete frozen league."""
    if state.results:
        raise ValueError("rosters are locked after the first league game")
    if outgoing_card_id == incoming_card_id:
        raise ValueError("incoming and outgoing cards must differ")
    target = next((team for team in state.teams if team.config.team_id == team_id), None)
    if target is None:
        raise ValueError(f"unknown Manager team: {team_id}")
    if outgoing_card_id not in target.config.roster.all_card_ids:
        raise ValueError("outgoing card is not on the selected team")
    claimed_elsewhere = {
        card_id
        for team in state.teams
        if team.config.team_id != team_id
        for card_id in team.config.roster.all_card_ids
    }
    if incoming_card_id in claimed_elsewhere:
        raise ValueError("incoming card is already owned by another league team")
    catalog.get(incoming_card_id)

    roster = target.config.roster
    groups = {
        "batter": roster.batter_card_ids,
        "rotation": roster.rotation_card_ids,
        "bullpen": roster.bullpen_card_ids,
    }
    group = next(name for name, cards in groups.items() if outgoing_card_id in cards)
    groups[group] = tuple(
        incoming_card_id if card_id == outgoing_card_id else card_id
        for card_id in groups[group]
    )
    replacement = RosterSelection(
        groups["batter"], groups["rotation"], groups["bullpen"]
    )
    lineup = tuple(
        replace(entry, card_id=incoming_card_id)
        if entry.card_id == outgoing_card_id
        else entry
        for entry in target.config.lineup
    )
    configs = tuple(
        replace(team.config, roster=replacement, lineup=lineup, strategy="custom")
        if team.config.team_id == team_id
        else team.config
        for team in state.teams
    )
    return create_manager_league(catalog, configs, seed=state.seed)
