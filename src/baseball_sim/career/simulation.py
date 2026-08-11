"""Deterministic per-game and per-season career controls."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from baseball_sim.game.engine import apply_outcome
from baseball_sim.game.simulation import counter_uniform
from baseball_sim.game.state import GameState
from baseball_sim.simulation.matchup import (
    BatterRatings,
    PitcherRatings,
    matchup_probabilities,
)
from baseball_sim.simulation.outcomes import Outcome

from .models import (
    ActiveCareerGame,
    BatterSkillScores,
    BattingStats,
    CareerEvent,
    CareerRetiredEvent,
    CareerState,
    GamePlayedEvent,
    PlateAppearancePlayedEvent,
    RatingImprovedEvent,
    SeasonAdvancedEvent,
    SeasonRecord,
    initial_state,
)
from .progression import DEVELOPMENT_BANK_CAP, spend_development_points

DEFAULT_PLATE_APPEARANCES = 4  # Retained as a compatibility-only request field.
CAREER_GAME_FIXTURE_VERSION = "career-neutral-game-v0.1"


def _new_game(state: CareerState) -> ActiveCareerGame:
    player = state.origin.profile.player_id
    prefix = f"{player}:{state.season_year}:{state.games_played + 1}"
    away = (player,) + tuple(f"{prefix}:teammate:{index}" for index in range(2, 10))
    home = tuple(f"{prefix}:opponent:{index}" for index in range(1, 10))
    # The M3 counter sampler also keys on the season/game-specific lineup namespace and
    # PA counter, so a resumed game follows the exact same sequence.
    seed = state.origin.seed ^ (state.season_year << 16) ^ (state.games_played + 1)
    game = GameState(
        away_lineup=away,
        home_lineup=home,
        away_pitcher=f"{prefix}:away-pitcher",
        home_pitcher=f"{prefix}:opponent-pitcher",
        seed=seed,
        rating_snapshot_version=CAREER_GAME_FIXTURE_VERSION,
    )
    return ActiveCareerGame(state.season_year, state.games_played + 1, game, ())


def _cards(
    state: CareerState, active: ActiveCareerGame
) -> tuple[dict[str, BatterRatings], dict[str, PitcherRatings]]:
    neutral = BatterRatings()
    lineups = active.game_state.away_lineup + active.game_state.home_lineup
    batters = {player: neutral for player in lineups}
    ratings = state.ratings
    batters[state.origin.profile.player_id] = BatterRatings(
        ratings.contact, ratings.power, ratings.eye
    )
    pitchers = {
        active.game_state.away_pitcher: PitcherRatings(),
        active.game_state.home_pitcher: PitcherRatings(),
    }
    return batters, pitchers


@lru_cache(maxsize=64)
def _probability_values(
    batter: BatterRatings, pitcher: PitcherRatings
) -> tuple[float, ...]:
    return matchup_probabilities(batter, pitcher).values


def _sample(probabilities: tuple[float, ...], draw: float) -> Outcome:
    cumulative = 0.0
    for outcome, probability in zip(Outcome, probabilities, strict=True):
        cumulative += probability
        if draw < cumulative:
            return outcome
    return Outcome.HR


def _game_rewards(stats: BattingStats) -> tuple[int, int]:
    # Participation, not performance, drives development. This avoids a rich-get-richer
    # loop where better ratings earn more points simply because they create more hits.
    xp = stats.pa
    return xp, 0


def _apply_game_event(state: CareerState, event: GamePlayedEvent) -> CareerState:
    if event.season_year != state.season_year:
        raise ValueError("game event season does not match the current season")
    if event.game_number != state.games_played + 1:
        raise ValueError("game events must be applied in schedule order")
    if state.games_played >= state.origin.season_games:
        raise ValueError("the current season schedule is complete")
    active = state.active_game
    if active is None or not active.game_state.finished:
        raise ValueError("game completion requires a finished M3 game")
    if event.outcomes != active.career_outcomes:
        raise ValueError("game event does not match the active game")
    if event.plate_appearances != len(event.outcomes) or event.plate_appearances <= 0:
        raise ValueError("game event plate appearances are invalid")
    game_stats = BattingStats.from_outcomes(event.outcomes)
    expected_xp, _unused = _game_rewards(game_stats)
    if event.xp_earned != expected_xp:
        raise ValueError("game event XP does not match its outcomes")
    awarded = sum(
        item.development_points_earned
        for item in state.events
        if isinstance(item, PlateAppearancePlayedEvent)
        and item.season_year == state.season_year
        and item.game_number == active.game_number
    )
    if event.development_points_earned != awarded:
        raise ValueError("game event development points do not match XP thresholds")
    return replace(
        state,
        games_played=state.games_played + 1,
        active_game=None,
        season_stats=state.season_stats + game_stats,
        career_stats=state.career_stats + game_stats,
        events=state.events + (event,),
    )


def _apply_pa_event(state: CareerState, event: PlateAppearancePlayedEvent) -> CareerState:
    if state.retired:
        raise ValueError("the career is retired")
    if state.games_played >= state.origin.season_games:
        raise ValueError("the current season schedule is complete")
    active = state.active_game
    if active is None:
        active = _new_game(state)
    if (
        event.season_year != state.season_year
        or event.game_number != active.game_number
        or event.pa_index != active.game_state.plate_appearances
    ):
        raise ValueError("plate-appearance event does not match the active game")
    if (
        event.batter != active.game_state.batter
        or event.pitcher != active.game_state.pitcher
        or event.career_plate_appearance
        != (event.batter == state.origin.profile.player_id)
    ):
        raise ValueError("plate-appearance participants do not match the M3 game")
    transition = apply_outcome(active.game_state, event.outcome)
    xp_increment = int(event.career_plate_appearance)
    crossed = (
        (state.experience + xp_increment) // 60 - state.experience // 60
    )
    awarded = min(crossed, DEVELOPMENT_BANK_CAP - state.development_points)
    expired = crossed - awarded
    if (
        event.development_points_earned != awarded
        or event.development_points_expired != expired
    ):
        raise ValueError("plate-appearance development rewards are invalid")
    updated = ActiveCareerGame(
        active.season_year,
        active.game_number,
        transition.state,
        active.career_outcomes
        + ((event.outcome,) if event.career_plate_appearance else ()),
    )
    return replace(
        state,
        experience=state.experience + xp_increment,
        development_points=state.development_points + awarded,
        expired_development_points=state.expired_development_points + expired,
        active_game=updated,
        events=state.events + (event,),
    )


def _next_game_pa(
    state: CareerState,
    *,
    plate_appearances: int = DEFAULT_PLATE_APPEARANCES,
    opponent: PitcherRatings | None = None,
) -> CareerState:
    """Play one internal M3 PA and autosettle when that game finishes."""
    if not 1 <= plate_appearances <= 12:
        raise ValueError("plate_appearances must be between 1 and 12")
    if state.retired:
        raise ValueError("the career is retired")
    if state.games_played >= state.origin.season_games:
        raise ValueError("the current season schedule is complete")
    active = state.active_game or _new_game(state)
    batters, pitchers = _cards(state, active)
    if opponent is not None:
        pitchers[active.game_state.home_pitcher] = opponent
    game_number = state.games_played + 1
    game = active.game_state
    probabilities = _probability_values(batters[game.batter], pitchers[game.pitcher])
    draw = counter_uniform(
        game.seed, game.plate_appearances, "pa-outcome", game.simulation_model_version
    )
    transition = apply_outcome(game, _sample(probabilities, draw))
    is_career_pa = transition.batter == state.origin.profile.player_id
    xp_increment = int(is_career_pa)
    crossed = (
        (state.experience + xp_increment) // 60 - state.experience // 60
    )
    awarded = min(crossed, DEVELOPMENT_BANK_CAP - state.development_points)
    state = _apply_pa_event(
        state,
        PlateAppearancePlayedEvent(
            state.season_year,
            game_number,
            active.game_state.plate_appearances,
            transition.outcome,
            transition.batter,
            transition.pitcher,
            is_career_pa,
            awarded,
            crossed - awarded,
        ),
    )
    completed = state.active_game
    if completed is None or not completed.game_state.finished:
        return state
    game_stats = BattingStats.from_outcomes(completed.career_outcomes)
    xp, _unused = _game_rewards(game_stats)
    points = sum(
        event.development_points_earned
        for event in state.events
        if isinstance(event, PlateAppearancePlayedEvent)
        and event.season_year == state.season_year
        and event.game_number == completed.game_number
    )
    event = GamePlayedEvent(
        season_year=state.season_year,
        game_number=game_number,
        plate_appearances=len(completed.career_outcomes),
        outcomes=completed.career_outcomes,
        xp_earned=xp,
        development_points_earned=points,
    )
    return _apply_game_event(state, event)


def next_pa(
    state: CareerState,
    *,
    plate_appearances: int = DEFAULT_PLATE_APPEARANCES,
    opponent: PitcherRatings | None = None,
) -> CareerState:
    """Complete the created player's next PA, simulating intervening M3 PAs."""
    starting_xp = state.experience
    starting_games = state.games_played
    result = state
    for _ in range(1_000):
        result = _next_game_pa(
            result, plate_appearances=plate_appearances, opponent=opponent
        )
        if result.experience > starting_xp or result.games_played > starting_games:
            return result
    raise RuntimeError("career game exceeded the plate-appearance safety limit")


def play_game(
    state: CareerState,
    *,
    plate_appearances: int = DEFAULT_PLATE_APPEARANCES,
    opponent: PitcherRatings | None = None,
) -> CareerState:
    """Quick-sim the remainder of the current game, or one new game."""
    starting_games = state.games_played
    result = state
    while result.games_played == starting_games:
        result = next_pa(
            result, plate_appearances=plate_appearances, opponent=opponent
        )
    return result


def simulate_games(
    state: CareerState,
    games: int,
    *,
    plate_appearances: int = DEFAULT_PLATE_APPEARANCES,
) -> CareerState:
    if games <= 0:
        raise ValueError("games must be positive")
    if state.games_played + games > state.origin.season_games:
        raise ValueError("requested games exceed the current season schedule")
    result = state
    for _ in range(games):
        result = play_game(result, plate_appearances=plate_appearances)
    return result


def simulate_to_season_end(
    state: CareerState, *, plate_appearances: int = DEFAULT_PLATE_APPEARANCES
) -> CareerState:
    remaining = state.origin.season_games - state.games_played
    if remaining == 0:
        return state
    return simulate_games(state, remaining, plate_appearances=plate_appearances)


def simulate_week(
    state: CareerState,
    games: int = 6,
    *,
    plate_appearances: int = DEFAULT_PLATE_APPEARANCES,
) -> CareerState:
    if not 1 <= games <= 6:
        raise ValueError("a simulated week must contain between one and six games")
    remaining = state.origin.season_games - state.games_played
    if remaining <= 0:
        raise ValueError("the current season schedule is complete")
    return simulate_games(
        state, min(games, remaining), plate_appearances=plate_appearances
    )


def simulate_to_next_event(
    state: CareerState, *, plate_appearances: int = DEFAULT_PLATE_APPEARANCES
) -> CareerState:
    """Advance to the first DP threshold, completed game, or season boundary."""
    if state.retired:
        raise ValueError("the career is retired")
    if state.games_played >= state.origin.season_games:
        return advance_season(state)
    starting_games = state.games_played
    starting_points = state.development_points + state.expired_development_points
    result = state
    for _ in range(1_000):
        result = next_pa(result, plate_appearances=plate_appearances)
        points = result.development_points + result.expired_development_points
        if result.games_played > starting_games or points > starting_points:
            return result
    raise RuntimeError("career game exceeded the plate-appearance safety limit")


def _apply_season_advanced_event(
    state: CareerState, event: SeasonAdvancedEvent
) -> CareerState:
    if state.games_played != state.origin.season_games:
        raise ValueError("a season must be complete before advancing")
    if event.previous_year != state.season_year or event.next_year != state.season_year + 1:
        raise ValueError("season event years are invalid")
    if event.new_age != state.age + 1:
        raise ValueError("season event age is invalid")
    record = SeasonRecord(state.season_year, state.age, state.scores, state.season_stats)
    drift = _age_drift(state.age)
    next_scores = BatterSkillScores(
        contact=max(-10.0, state.scores.contact + drift.contact),
        power=max(-10.0, state.scores.power + drift.power),
        eye=max(-10.0, state.scores.eye + drift.eye),
        speed_proxy=max(-10.0, state.scores.speed_proxy + drift.speed_proxy),
    )
    return replace(
        state,
        age=event.new_age,
        season_year=event.next_year,
        games_played=0,
        scores=next_scores,
        season_stats=BattingStats(),
        season_purchases=0,
        season_skill_purchases=(0, 0, 0, 0),
        completed_seasons=state.completed_seasons + (record,),
        events=state.events + (event,),
    )


def advance_season(state: CareerState) -> CareerState:
    if state.retired:
        raise ValueError("the career is retired")
    if state.active_game is not None:
        raise ValueError("a season cannot advance during an active game")
    if len(state.completed_seasons) + 1 >= 20:
        return _apply_retired_event(
            state, CareerRetiredEvent(state.season_year, state.age)
        )
    return _apply_season_advanced_event(
        state,
        SeasonAdvancedEvent(state.season_year, state.season_year + 1, state.age + 1),
    )


def _apply_retired_event(state: CareerState, event: CareerRetiredEvent) -> CareerState:
    if state.games_played != state.origin.season_games:
        raise ValueError("a season must be complete before retirement")
    if event.season_year != state.season_year or event.age != state.age:
        raise ValueError("retirement event does not match career state")
    if len(state.completed_seasons) + 1 != 20:
        raise ValueError("retirement requires exactly twenty completed seasons")
    record = SeasonRecord(state.season_year, state.age, state.scores, state.season_stats)
    return replace(
        state,
        completed_seasons=state.completed_seasons + (record,),
        events=state.events + (event,),
    )


def _age_drift(age: int) -> BatterSkillScores:
    """Conservative v0.1 age curve informed by adjacent CPBL player-seasons."""
    if age <= 21:
        return BatterSkillScores(0.10, 0.08, 0.06, 0.00)
    if age <= 24:
        return BatterSkillScores(0.05, 0.04, 0.06, -0.01)
    if age <= 27:
        return BatterSkillScores(0.02, 0.00, 0.02, -0.03)
    if age <= 30:
        return BatterSkillScores(0.00, -0.02, 0.00, -0.05)
    if age <= 33:
        return BatterSkillScores(-0.04, -0.06, -0.02, -0.07)
    if age <= 36:
        return BatterSkillScores(-0.08, -0.10, -0.06, -0.12)
    if age <= 39:
        return BatterSkillScores(-0.12, -0.14, -0.08, -0.15)
    return BatterSkillScores(-0.16, -0.20, -0.10, -0.18)


def simulate_season(
    state: CareerState, *, plate_appearances: int = DEFAULT_PLATE_APPEARANCES
) -> CareerState:
    """Finish the current season and advance to opening day of the next year."""
    return advance_season(
        simulate_to_season_end(state, plate_appearances=plate_appearances)
    )


def replay_career(origin_state: CareerState, events: tuple[CareerEvent, ...]) -> CareerState:
    """Rebuild a career from its immutable origin and explicit event stream."""
    if origin_state.events or origin_state.games_played or origin_state.completed_seasons:
        raise ValueError("replay requires an unmodified origin state")
    state = initial_state(origin_state.origin)
    for event in events:
        if isinstance(event, PlateAppearancePlayedEvent):
            state = _apply_pa_event(state, event)
        elif isinstance(event, GamePlayedEvent):
            state = _apply_game_event(state, event)
        elif isinstance(event, RatingImprovedEvent):
            if state.scores.get(event.skill) != event.score_before:
                raise ValueError("rating event does not match replay state")
            state = spend_development_points(state, event.skill, event.purchases)
            generated = state.events[-1]
            if not isinstance(generated, RatingImprovedEvent) or generated != event:
                raise ValueError("rating event result does not match the model version")
        elif isinstance(event, SeasonAdvancedEvent):
            state = _apply_season_advanced_event(state, event)
        elif isinstance(event, CareerRetiredEvent):
            state = _apply_retired_event(state, event)
        else:
            raise TypeError("unknown career event")
    return state
