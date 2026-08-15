from __future__ import annotations

from baseball_sim.career import (
    BaserunningStrategy,
    BatterArchetype,
    Handedness,
    create_career,
    play_game,
    replay_career,
)
from baseball_sim.career.simulation import _steal_rates


def _career(seed: int = 42):
    return create_career(
        player_id="runner-1",
        name="Runner",
        position="CF",
        bats=Handedness.LEFT,
        throws=Handedness.RIGHT,
        archetype=BatterArchetype.SPEED,
        age=18,
        season_year=2026,
        seed=seed,
        season_games=20,
    )


def test_speed_and_strategy_raise_attempt_and_success_rates() -> None:
    low = _steal_rates(55, BaserunningStrategy.CONSERVATIVE, 1)
    high = _steal_rates(100, BaserunningStrategy.AGGRESSIVE, 1)
    assert high[0] > low[0]
    assert high[1] > low[1]


def test_baserunning_stats_survive_event_replay() -> None:
    origin = _career(seed=101)
    completed = play_game(origin)
    replayed = replay_career(origin, completed.events)
    assert replayed == completed
    assert completed.season_stats.stolen_bases >= 0
    assert completed.season_stats.caught_stealing >= 0
    assert completed.season_stats.runs >= 0
    assert completed.season_stats.rbi >= 0
