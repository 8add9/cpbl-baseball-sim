from __future__ import annotations

from dataclasses import replace

from baseball_sim.game import GameState, counter_uniform, simulate_game, simulate_next_pa
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings


def _fixture(
    seed: int = 42,
) -> tuple[GameState, dict[str, BatterRatings], dict[str, PitcherRatings]]:
    away = tuple(f"A{index}" for index in range(1, 10))
    home = tuple(f"H{index}" for index in range(1, 10))
    state = GameState(away, home, "AP", "HP", seed=seed, rating_snapshot_version="fixture-v1")
    batters = {player: BatterRatings() for player in away + home}
    pitchers = {"AP": PitcherRatings(), "HP": PitcherRatings()}
    return state, batters, pitchers


def test_full_game_is_reproducible_from_seed_and_cards() -> None:
    state, batters, pitchers = _fixture()
    first = simulate_game(state, batters, pitchers)
    second = simulate_game(state, batters, pitchers)
    assert first == second
    assert first.final_state.finished
    assert first.final_state.winner is not None
    assert first.final_state.plate_appearances == len(first.transitions)


def test_save_resume_matches_uninterrupted_game() -> None:
    state, batters, pitchers = _fixture()
    uninterrupted = simulate_game(state, batters, pitchers)

    paused = state
    prefix = []
    for _ in range(25):
        transition = simulate_next_pa(paused, batters, pitchers)
        prefix.append(transition)
        paused = transition.state
    resumed = simulate_game(paused, batters, pitchers)

    assert tuple(prefix) + resumed.transitions == uninterrupted.transitions
    assert resumed.final_state == uninterrupted.final_state


def test_seed_and_draw_channels_are_independent() -> None:
    draw = counter_uniform(42, 10, "pa-outcome", "pa-hierarchical-v0.1")
    assert draw == counter_uniform(42, 10, "pa-outcome", "pa-hierarchical-v0.1")
    assert draw != counter_uniform(43, 10, "pa-outcome", "pa-hierarchical-v0.1")
    assert draw != counter_uniform(42, 10, "runner-advance", "pa-hierarchical-v0.1")


def test_different_seed_changes_full_game_sequence() -> None:
    state, batters, pitchers = _fixture()
    other = replace(state, seed=43)
    first = simulate_game(state, batters, pitchers)
    second = simulate_game(other, batters, pitchers)
    assert [event.outcome for event in first.transitions] != [
        event.outcome for event in second.transitions
    ]
