"""Application services over the single authoritative Manager league domain."""

from __future__ import annotations

from dataclasses import replace

from .cards import CardCatalog
from .customization import (
    AI_CPBL_TEAM_NAMES,
    rename_team,
    roster_limits_for_name,
    set_rotation_plan,
    set_starting_lineup,
)
from .franchise import TeamEntitlement
from .game_roster import LineupEntry
from .league import (
    ManagerLeagueState,
    ManagerTeamConfig,
    create_manager_league,
    simulate_manager_season,
    start_next_manager_season,
)
from .league import simulate_next_league_game as simulate_next_domain_game
from .optimizer import RosterStrategy, build_optimized_roster
from .roster import RosterRules, RosterSelection, evaluate_roster


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
                name=AI_CPBL_TEAM_NAMES[index],
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
    _validate_active_rosters(state)
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
    _validate_active_rosters(state)
    return simulate_manager_season(state)


def simulate_next_league_game(
    state: ManagerLeagueState, _catalog: CardCatalog
) -> ManagerLeagueState:
    _validate_active_rosters(state)
    return simulate_next_domain_game(state)


def _entitlement(state: ManagerLeagueState, team_id: str) -> TeamEntitlement:
    assert state.franchise is not None
    return next(item for item in state.franchise.entitlements if item.team_id == team_id)


def _rules_for_team(state: ManagerLeagueState, team_id: str) -> RosterRules:
    team = next(item for item in state.teams if item.config.team_id == team_id)
    entitlement = _entitlement(state, team_id)
    limits = roster_limits_for_name(
        team.config.name or team_id,
        cost_bonus=entitlement.cost_budget_bonus,
        ssr_bonus=entitlement.ssr_cap_bonus,
    )
    selection = team.config.roster
    return RosterRules(
        roster_size=len(selection.all_card_ids),
        batter_count=len(selection.batter_card_ids),
        rotation_count=4,
        bullpen_count=5,
        budget=limits.cost_limit,
        max_ssr=limits.ssr_limit,
        max_sr=5,
    )


def _validate_active_rosters(state: ManagerLeagueState) -> None:
    for team in state.teams:
        legality = evaluate_roster(
            state.catalog,
            team.config.roster,
            _rules_for_team(state, team.config.team_id),
        )
        if not legality.legal:
            raise ValueError(
                f"illegal active roster for {team.config.name}: {legality.violations}"
            )


def rename_user_team(state: ManagerLeagueState, display_name: str) -> ManagerLeagueState:
    teams = tuple(
        replace(team, config=rename_team(team.config, display_name))
        if team.config.team_id == state.user_team_id
        else team
        for team in state.teams
    )
    return replace(state, teams=teams)


def update_user_lineup(
    state: ManagerLeagueState, lineup: tuple[LineupEntry, ...]
) -> ManagerLeagueState:
    target = next(team for team in state.teams if team.config.team_id == state.user_team_id)
    validated = set_starting_lineup(state.catalog, target.config.roster, lineup)
    teams = tuple(
        replace(team, config=replace(team.config, lineup=validated, strategy="custom"))
        if team.config.team_id == state.user_team_id
        else team
        for team in state.teams
    )
    return replace(state, teams=teams)


def update_user_rotation_plan(
    state: ManagerLeagueState, starter_card_ids: tuple[str, ...]
) -> ManagerLeagueState:
    target = next(team for team in state.teams if team.config.team_id == state.user_team_id)
    plan = set_rotation_plan(target.config.roster, starter_card_ids)
    plans = tuple(
        (team_id, plan.starter_card_ids if team_id == state.user_team_id else current)
        for team_id, current in state.rotation_plans
    )
    return replace(state, rotation_plans=plans)


def advance_manager_season(
    state: ManagerLeagueState, _catalog: CardCatalog
) -> ManagerLeagueState:
    _validate_active_rosters(state)
    return start_next_manager_season(state)


def replace_team_card(
    state: ManagerLeagueState,
    catalog: CardCatalog,
    *,
    team_id: str,
    outgoing_card_id: str,
    incoming_card_id: str,
) -> ManagerLeagueState:
    """Replace one card between games and keep pitcher tracking replayable."""
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
    availability = target.pitcher_availability
    if group == "rotation":
        starts = dict(availability.last_start_games)
        previous = starts.pop(outgoing_card_id)
        starts[incoming_card_id] = previous
        availability = replace(
            availability,
            rotation_card_ids=groups["rotation"],
            last_start_games=tuple(
                (card_id, starts[card_id]) for card_id in groups["rotation"]
            ),
        )
    elif group == "bullpen":
        streaks = dict(availability.relief_streaks)
        previous = streaks.pop(outgoing_card_id)
        streaks[incoming_card_id] = previous
        availability = replace(
            availability,
            bullpen_card_ids=groups["bullpen"],
            relief_streaks=tuple(
                (card_id, streaks[card_id]) for card_id in groups["bullpen"]
            ),
        )
    legality = evaluate_roster(catalog, replacement, _rules_for_team(state, team_id))
    if not legality.legal:
        raise ValueError(f"illegal replacement roster: {legality.violations}")
    teams = tuple(
        replace(
            team,
            config=replace(
                team.config,
                roster=replacement,
                lineup=lineup,
                strategy="custom",
            ),
            pitcher_availability=availability,
        )
        if team.config.team_id == team_id
        else team
        for team in state.teams
    )
    plans = tuple(
        (
            plan_team_id,
            tuple(
                incoming_card_id if card_id == outgoing_card_id else card_id
                for card_id in plan
            ),
        )
        if plan_team_id == team_id
        else (plan_team_id, plan)
        for plan_team_id, plan in state.rotation_plans
    )
    return replace(state, teams=teams, rotation_plans=plans)
