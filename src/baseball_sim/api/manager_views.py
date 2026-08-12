"""Manager domain projections for HTTP responses."""

from __future__ import annotations

from collections import Counter

from baseball_sim.manager.cards import CardCatalog, CatalogEntry
from baseball_sim.manager.roster import evaluate_roster
from baseball_sim.manager.usage import available_bullpen, select_next_starter

from .manager_repository import ManagerRecord
from .manager_schemas import (
    LineupCardView,
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
    teams: list[ManagerTeamView] = []
    for team_state in state.teams:
        config = team_state.config
        selection = config.roster
        legality = evaluate_roster(catalog, selection)
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
                next_starter_card_id=select_next_starter(
                    team_state.pitcher_availability
                ),
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
    )
