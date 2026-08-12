"""Manager domain projections for HTTP responses."""

from __future__ import annotations

from collections import Counter

from baseball_sim.manager.cards import CardCatalog, CatalogEntry
from baseball_sim.manager.customization import roster_limits_for_name
from baseball_sim.manager.roster import evaluate_roster
from baseball_sim.manager.usage import available_bullpen

from .manager_repository import ManagerRecord
from .manager_schemas import (
    LineupCardView,
    ManagerPlayerStatView,
    ManagerTeamView,
    ManagerViewResponse,
    ResultView,
    RosterCardView,
    ScheduledGameView,
    StandingView,
)


def _abilities(entry: CatalogEntry) -> dict[str, float]:
    return {
        name: ability.rating_raw for name, ability in entry.card.abilities.items()
    }


def roster_card_view(entry: CatalogEntry) -> RosterCardView:
    card = entry.card
    return RosterCardView(
        card_id=card.card_id,
        player_name=card.player_name,
        season_year=card.season_year,
        team=card.team,
        profile_position="/".join(card.profile_positions),
        role=None if card.pitcher_role is None else card.pitcher_role.value,
        tier="" if entry.tier is None else entry.tier.value,
        cost=entry.cost or 0,
        abilities=_abilities(entry),
    )


def manager_view(record: ManagerRecord, catalog: CardCatalog) -> ManagerViewResponse:
    state = record.state
    next_game = state.next_game
    assert state.franchise is not None
    entitlements = {item.team_id: item for item in state.franchise.entitlements}
    rotation_plans = dict(state.rotation_plans)
    teams: list[ManagerTeamView] = []
    for team_state in state.teams:
        config = team_state.config
        selection = config.roster
        entitlement = entitlements[config.team_id]
        limits = roster_limits_for_name(
            config.name or config.team_id,
            cost_bonus=entitlement.cost_budget_bonus,
            ssr_bonus=entitlement.ssr_cap_bonus,
        )
        legality = evaluate_roster(catalog, selection)
        rotation_plan = rotation_plans[config.team_id]
        lineup_ids = {entry.card_id for entry in config.lineup}
        lineup: list[LineupCardView] = []
        for lineup_entry in config.lineup:
            entry = catalog.get(lineup_entry.card_id)
            card = entry.card
            lineup.append(
                LineupCardView(
                    card_id=card.card_id,
                    player_name=card.player_name,
                    season_year=card.season_year,
                    position=lineup_entry.position,
                    profile_position="/".join(card.profile_positions),
                    role=None,
                    tier="" if entry.tier is None else entry.tier.value,
                    cost=entry.cost or 0,
                    abilities=_abilities(entry),
                )
            )
        all_entries = [catalog.get(card_id) for card_id in selection.all_card_ids]
        tiers = Counter(
            entry.tier.value for entry in all_entries if entry.tier is not None
        )
        teams.append(
            ManagerTeamView(
                team_id=config.team_id,
                name=config.name or config.team_id,
                strategy=config.strategy,
                games_played=team_state.pitcher_availability.team_games_played,
                roster_cost=legality.total_cost,
                batter_count=len(selection.batter_card_ids),
                rotation_count=len(selection.rotation_card_ids),
                bullpen_count=len(selection.bullpen_card_ids),
                next_starter_card_id=rotation_plan[
                    team_state.pitcher_availability.team_games_played % 4
                ],
                lineup=lineup,
                bench=[
                    roster_card_view(catalog.get(card_id))
                    for card_id in selection.batter_card_ids
                    if card_id not in lineup_ids
                ],
                rotation=[
                    roster_card_view(catalog.get(card_id))
                    for card_id in selection.rotation_card_ids
                ],
                bullpen=[
                    roster_card_view(catalog.get(card_id))
                    for card_id in selection.bullpen_card_ids
                ],
                tier_counts={tier: tiers.get(tier, 0) for tier in ("N", "R", "SR", "SSR")},
                available_bullpen_card_ids=list(
                    available_bullpen(team_state.pitcher_availability)
                ),
                rotation_plan=list(rotation_plan),
                cost_limit=limits.cost_limit,
                ssr_limit=limits.ssr_limit,
                sr_limit=None if limits.unlimited else 5,
                unlimited_roster=limits.unlimited,
            )
        )
    player_stats: list[ManagerPlayerStatView] = []
    team_names = {team.config.team_id: team.config.name for team in state.teams}
    owner_by_card = {
        card_id: team.config.team_id
        for team in state.teams
        for card_id in team.config.roster.all_card_ids
    }
    for item in state.player_stats:
        card = catalog.get(item.card_id).card
        if item.batter is not None:
            batter_line = item.batter
            values: dict[str, int | float | str] = {
                "G": batter_line.games,
                "PA": batter_line.pa,
                "AB": batter_line.ab,
                "H": batter_line.hits,
                "2B": batter_line.doubles,
                "3B": batter_line.triples,
                "HR": batter_line.home_runs,
                "BB": batter_line.walks,
                "HBP": batter_line.hbp,
                "SO": batter_line.strikeouts,
                "AVG": batter_line.avg,
                "OBP": batter_line.obp,
                "SLG": batter_line.slg,
                "OPS": batter_line.ops,
            }
            kind = "batter"
        else:
            assert item.pitcher is not None
            pitcher_line = item.pitcher
            values = {
                "G": pitcher_line.games,
                "GS": pitcher_line.games_started,
                "W": pitcher_line.wins,
                "L": pitcher_line.losses,
                "IP": pitcher_line.innings_pitched,
                "BF": pitcher_line.batters_faced,
                "H": pitcher_line.hits,
                "HR": pitcher_line.home_runs,
                "BB": pitcher_line.walks,
                "HBP": pitcher_line.hbp,
                "SO": pitcher_line.strikeouts,
                "R": pitcher_line.runs,
                "RA9": pitcher_line.runs_allowed_per_nine,
                "WHIP": pitcher_line.whip,
            }
            kind = "pitcher"
        team_id = item.team_id or owner_by_card.get(item.card_id, "legacy-unknown")
        player_stats.append(
            ManagerPlayerStatView(
                card_id=item.card_id,
                player_name=card.player_name,
                card_season_year=card.season_year,
                team_id=team_id,
                team_name=team_names.get(team_id) or "歷史資料（球隊未記錄）",
                kind=kind,
                values=values,
            )
        )
    return ManagerViewResponse(
        manager_id=record.manager_id,
        revision=record.revision,
        autosaved_at=record.autosaved_at,
        persistence_version=record.persistence_version,
        schema_version=1,
        model_version=state.version,
        catalog_snapshot_version=catalog.snapshot_version,
        catalog_fingerprint=catalog.fingerprint,
        seed=state.seed,
        season_year=state.season_year,
        user_team_id=state.user_team_id,
        games_completed=len(state.results),
        total_games=len(state.schedule),
        finished=state.finished,
        next_game=(
            None
            if next_game is None
            else ScheduledGameView(
                game_number=next_game.game_number,
                round_number=next_game.round_number,
                away_team_id=next_game.away_team_id,
                home_team_id=next_game.home_team_id,
            )
        ),
        standings=[
            StandingView(
                rank=index,
                team_id=row.team_id,
                wins=row.wins,
                losses=row.losses,
                runs_scored=row.runs_scored,
                runs_allowed=row.runs_allowed,
                run_differential=row.run_differential,
                winning_percentage=row.winning_percentage,
                games_behind=row.games_behind,
            )
            for index, row in enumerate(state.standings.rows, start=1)
        ],
        teams=teams,
        recent_results=[
            ResultView(
                game_number=result.game_number,
                away_team_id=result.away_team_id,
                home_team_id=result.home_team_id,
                away_runs=result.away_runs,
                home_runs=result.home_runs,
            )
            for result in state.results[-10:]
        ],
        player_stats=player_stats,
    )
