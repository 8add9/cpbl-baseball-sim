"""Thread-safe in-memory game sessions for the Phase 1 API."""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from uuid import uuid4

from baseball_sim.game.simulation import simulate_next_pa
from baseball_sim.game.state import GameState
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings


class GameNotFoundError(LookupError):
    """Raised when a requested session does not exist."""


class GameFinishedError(RuntimeError):
    """Raised when simulation is requested for a completed game."""


class SimulationLimitError(RuntimeError):
    """Raised when a bounded simulation cannot reach its terminal condition."""


@dataclass(frozen=True, slots=True)
class GameEvent:
    outcome: str
    batter: str
    pitcher: str
    runs_scored: int
    inning: int
    half: str
    description: str


@dataclass(slots=True)
class GameSession:
    game_id: str
    initial_state: GameState
    state: GameState
    batter_cards: dict[str, BatterRatings]
    pitcher_cards: dict[str, PitcherRatings]
    events: list[GameEvent]


def _neutral_fixture(seed: int) -> tuple[
    GameState, dict[str, BatterRatings], dict[str, PitcherRatings]
]:
    away = tuple(f"A{index}" for index in range(1, 10))
    home = tuple(f"H{index}" for index in range(1, 10))
    state = GameState(
        away_lineup=away,
        home_lineup=home,
        away_pitcher="AP",
        home_pitcher="HP",
        seed=seed,
        rating_snapshot_version="neutral-fixture-v1",
    )
    batter_cards = {player: BatterRatings() for player in away + home}
    pitcher_cards = {"AP": PitcherRatings(), "HP": PitcherRatings()}
    return state, batter_cards, pitcher_cards


def _description(outcome: str, batter: str, runs: int) -> str:
    action = {
        "BB": "獲得四壞球保送",
        "HBP": "遭觸身球保送",
        "SO": "遭到三振",
        "OUT": "擊球出局",
        "1B": "擊出一壘安打",
        "2B": "擊出二壘安打",
        "3B": "擊出三壘安打",
        "HR": "擊出全壘打",
    }[outcome]
    suffix = "" if runs == 0 else f"，帶回{runs}分"
    return f"{batter}{action}{suffix}。"


class InMemoryGameRepository:
    """Owns sessions and applies every mutation while holding one process-local lock."""

    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._lock = RLock()

    @staticmethod
    def _snapshot(session: GameSession) -> GameSession:
        """Return an isolated response snapshot while the repository lock is held."""
        return GameSession(
            game_id=session.game_id,
            initial_state=session.initial_state,
            state=session.state,
            batter_cards=dict(session.batter_cards),
            pitcher_cards=dict(session.pitcher_cards),
            events=list(session.events),
        )

    def create(self, seed: int) -> GameSession:
        with self._lock:
            game_id = str(uuid4())
            state, batters, pitchers = _neutral_fixture(seed)
            session = GameSession(game_id, state, state, batters, pitchers, [])
            self._sessions[game_id] = session
            return self._snapshot(session)

    def get(self, game_id: str) -> GameSession:
        with self._lock:
            try:
                return self._snapshot(self._sessions[game_id])
            except KeyError as error:
                raise GameNotFoundError(game_id) from error

    def _get_unlocked(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except KeyError as error:
            raise GameNotFoundError(game_id) from error

    def _advance_unlocked(self, session: GameSession) -> None:
        if session.state.finished:
            raise GameFinishedError(session.game_id)
        before = session.state
        transition = simulate_next_pa(before, session.batter_cards, session.pitcher_cards)
        session.state = transition.state
        session.events.append(
            GameEvent(
                outcome=transition.outcome.value,
                batter=transition.batter,
                pitcher=transition.pitcher,
                runs_scored=transition.runs_scored,
                inning=before.inning,
                half=before.half.value,
                description=_description(
                    transition.outcome.value, transition.batter, transition.runs_scored
                ),
            )
        )

    def next_pa(self, game_id: str) -> GameSession:
        with self._lock:
            session = self._get_unlocked(game_id)
            self._advance_unlocked(session)
            return self._snapshot(session)

    def simulate_half(self, game_id: str, max_pa: int = 100) -> GameSession:
        with self._lock:
            session = self._get_unlocked(game_id)
            if session.state.finished:
                raise GameFinishedError(game_id)
            target = (session.state.inning, session.state.half)
            starting_state = session.state
            starting_events = len(session.events)
            for _ in range(max_pa):
                self._advance_unlocked(session)
                if session.state.finished or (session.state.inning, session.state.half) != target:
                    return self._snapshot(session)
            session.state = starting_state
            del session.events[starting_events:]
            raise SimulationLimitError("half inning exceeded the plate-appearance safety limit")

    def simulate_full(self, game_id: str, max_pa: int = 1_000) -> GameSession:
        with self._lock:
            session = self._get_unlocked(game_id)
            if session.state.finished:
                raise GameFinishedError(game_id)
            starting_state = session.state
            starting_events = len(session.events)
            for _ in range(max_pa):
                self._advance_unlocked(session)
                if session.state.finished:
                    return self._snapshot(session)
            session.state = starting_state
            del session.events[starting_events:]
            raise SimulationLimitError("game exceeded the plate-appearance safety limit")

    def reset(self, game_id: str, seed: int | None = None) -> GameSession:
        with self._lock:
            session = self._get_unlocked(game_id)
            reset_seed = session.initial_state.seed if seed is None else seed
            state = replace(session.initial_state, seed=reset_seed)
            session.state = state
            session.events.clear()
            return self._snapshot(session)
