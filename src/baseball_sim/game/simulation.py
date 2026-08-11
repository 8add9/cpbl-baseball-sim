"""Counter-based deterministic PA sampling connected to the pure game engine."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from baseball_sim.simulation.matchup import (
    BatterRatings,
    MatchupModel,
    PitcherRatings,
    matchup_probabilities,
)
from baseball_sim.simulation.outcomes import Outcome

from .engine import Transition, apply_outcome
from .state import GameState


@dataclass(frozen=True, slots=True)
class SimulatedGame:
    final_state: GameState
    transitions: tuple[Transition, ...]


def counter_uniform(
    seed: int, plate_appearance: int, channel: str, simulation_model_version: str
) -> float:
    """Stable [0,1) draw that does not persist mutable RNG implementation state."""
    payload = f"{seed}:{plate_appearance}:{channel}:{simulation_model_version}".encode()
    digest = hashlib.blake2b(payload, digest_size=8, person=b"cpblsim1").digest()
    return int.from_bytes(digest, "big") / 2**64


def _sample_outcome(probabilities: tuple[float, ...], draw: float) -> Outcome:
    cumulative = 0.0
    for outcome, probability in zip(Outcome, probabilities, strict=True):
        cumulative += probability
        if draw < cumulative:
            return outcome
    return list(Outcome)[-1]


def simulate_next_pa(
    state: GameState,
    batter_cards: Mapping[str, BatterRatings],
    pitcher_cards: Mapping[str, PitcherRatings],
    model: MatchupModel = MatchupModel.HIERARCHICAL,
) -> Transition:
    if state.finished:
        raise ValueError("cannot simulate a finished game")
    try:
        batter = batter_cards[state.batter]
        pitcher = pitcher_cards[state.pitcher]
    except KeyError as error:
        raise ValueError(f"missing rating card for {error.args[0]}") from error
    probabilities = matchup_probabilities(batter, pitcher, model)
    draw = counter_uniform(
        state.seed,
        state.plate_appearances,
        "pa-outcome",
        state.simulation_model_version,
    )
    return apply_outcome(state, _sample_outcome(probabilities.values, draw))


def simulate_game(
    initial: GameState,
    batter_cards: Mapping[str, BatterRatings],
    pitcher_cards: Mapping[str, PitcherRatings],
    model: MatchupModel = MatchupModel.HIERARCHICAL,
    max_plate_appearances: int = 1_000,
) -> SimulatedGame:
    if max_plate_appearances <= 0:
        raise ValueError("max_plate_appearances must be positive")
    state = initial
    transitions: list[Transition] = []
    while not state.finished and len(transitions) < max_plate_appearances:
        transition = simulate_next_pa(state, batter_cards, pitcher_cards, model)
        transitions.append(transition)
        state = transition.state
    if not state.finished:
        raise RuntimeError("game exceeded the plate-appearance safety limit")
    return SimulatedGame(state, tuple(transitions))
