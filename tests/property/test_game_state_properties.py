from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from baseball_sim.game import GameState, apply_outcome
from baseball_sim.simulation.outcomes import Outcome


@given(st.lists(st.sampled_from(list(Outcome)), min_size=0, max_size=300))
def test_arbitrary_outcome_stream_preserves_legal_state(outcomes: list[Outcome]) -> None:
    away = tuple(f"A{index}" for index in range(1, 10))
    home = tuple(f"H{index}" for index in range(1, 10))
    state = GameState(away, home, "AP", "HP")
    for outcome in outcomes:
        if state.finished:
            break
        before_pa = state.plate_appearances
        state = apply_outcome(state, outcome).state
        assert state.plate_appearances == before_pa + 1
        assert 0 <= state.outs <= 2
        assert state.inning >= 1
        assert state.away_score >= 0 and state.home_score >= 0
        assert len(state.bases) == 3
