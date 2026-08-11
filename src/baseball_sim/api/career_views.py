"""Career domain-to-HTTP projection functions."""

from __future__ import annotations

from baseball_sim.career.models import (
    BatterSkill,
    BattingStats,
    CareerState,
    GamePlayedEvent,
)
from baseball_sim.career.progression import (
    ABILITY_PURCHASE_CAP,
    SCORE_INCREMENT,
    SEASON_PURCHASE_CAP,
    purchase_cost,
)

from .career_repository import CareerRecord
from .career_schemas import (
    ActiveCareerGameView,
    BattingStatsView,
    CareerGameResultView,
    CareerSkillsView,
    CareerViewResponse,
    SkillView,
)


def _stats(stats: BattingStats) -> BattingStatsView:
    return BattingStatsView(
        games=stats.games,
        pa=stats.pa,
        ab=stats.ab,
        hits=stats.hits,
        singles=stats.singles,
        doubles=stats.doubles,
        triples=stats.triples,
        home_runs=stats.home_runs,
        walks=stats.walks,
        hbp=stats.hbp,
        strikeouts=stats.strikeouts,
        total_bases=stats.total_bases,
        avg=stats.avg,
        obp=stats.obp,
        slg=stats.slg,
        ops=stats.ops,
    )


def _skill(state: CareerState, skill: BatterSkill) -> SkillView:
    score = state.scores.get(skill)
    rating = state.ratings
    rating_raw = {
        BatterSkill.CONTACT: rating.contact,
        BatterSkill.POWER: rating.power,
        BatterSkill.EYE: rating.eye,
        BatterSkill.SPEED_PROXY: rating.speed_proxy,
    }[skill]
    index = list(BatterSkill).index(skill)
    potential = state.origin.potential_scores.get(skill)
    at_limit = (
        state.retired
        or skill is BatterSkill.SPEED_PROXY
        or state.season_purchases >= SEASON_PURCHASE_CAP
        or state.season_skill_purchases[index] >= ABILITY_PURCHASE_CAP
        or score + SCORE_INCREMENT > potential + 1e-12
    )
    cost = None if at_limit else purchase_cost(state, skill)
    return SkillView(
        score=score,
        rating_raw=rating_raw,
        rating_display=state.ratings.display[index],
        potential_score=potential,
        next_cost=cost,
        can_train=(
            cost is not None
            and state.active_game is None
            and state.development_points >= cost
        ),
    )


def _recent_results(state: CareerState) -> list[CareerGameResultView]:
    games = [event for event in state.events if isinstance(event, GamePlayedEvent)][-10:]
    results: list[CareerGameResultView] = []
    for event in games:
        stats = BattingStats.from_outcomes(event.outcomes)
        results.append(
            CareerGameResultView(
                season_year=event.season_year,
                game_number=event.game_number,
                plate_appearances=event.plate_appearances,
                outcomes=[outcome.value for outcome in event.outcomes],
                hits=stats.hits,
                home_runs=stats.home_runs,
                walks=stats.walks,
                xp_earned=event.xp_earned,
                development_points_earned=event.development_points_earned,
            )
        )
    return results


def career_view(record: CareerRecord) -> CareerViewResponse:
    state = record.state
    profile = state.origin.profile
    return CareerViewResponse(
        career_id=record.career_id,
        revision=record.revision,
        autosaved_at=record.autosaved_at,
        persistence_version=record.persistence_version,
        schema_version=state.schema_version,
        model_version=state.model_version,
        name=profile.name,
        position=profile.position,
        bats=profile.bats,
        throws=profile.throws,
        archetype=profile.archetype,
        age=state.age,
        season_year=state.season_year,
        games_played=state.games_played,
        season_games=state.origin.season_games,
        experience=state.experience,
        development_points=state.development_points,
        expired_development_points=state.expired_development_points,
        season_purchases=state.season_purchases,
        retired=state.retired,
        active_game=None
        if state.active_game is None
        else ActiveCareerGameView(
            season_year=state.active_game.season_year,
            game_number=state.active_game.game_number,
            inning=state.active_game.game_state.inning,
            half=state.active_game.game_state.half.value,
            outs=state.active_game.game_state.outs,
            bases=list(state.active_game.game_state.bases),
            away_score=state.active_game.game_state.away_score,
            home_score=state.active_game.game_state.home_score,
            batting_team=state.active_game.game_state.batting_team.value,
            batter=state.active_game.game_state.batter,
            pitcher=state.active_game.game_state.pitcher,
            away_pitcher=state.active_game.game_state.away_pitcher,
            home_pitcher=state.active_game.game_state.home_pitcher,
            seed=state.active_game.game_state.seed,
            game_plate_appearances=state.active_game.game_state.plate_appearances,
            career_plate_appearances=len(state.active_game.career_outcomes),
            career_outcomes=[
                outcome.value for outcome in state.active_game.career_outcomes
            ],
            away_lineup=list(state.active_game.game_state.away_lineup),
            home_lineup=list(state.active_game.game_state.home_lineup),
        ),
        skills=CareerSkillsView(
            contact=_skill(state, BatterSkill.CONTACT),
            power=_skill(state, BatterSkill.POWER),
            eye=_skill(state, BatterSkill.EYE),
            speed_proxy=_skill(state, BatterSkill.SPEED_PROXY),
        ),
        season_stats=_stats(state.season_stats),
        career_stats=_stats(state.career_stats),
        recent_results=_recent_results(state),
    )
