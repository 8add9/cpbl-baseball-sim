"""Durable SQLite adapter for ordinary text-game sessions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from baseball_sim.game.engine import apply_outcome
from baseball_sim.simulation.outcomes import Outcome

from .repository import (
    GameEvent,
    GameSession,
    InMemoryGameRepository,
    _description,
    _neutral_fixture,
)

GAME_PERSISTENCE_VERSION = "game-sqlite-v1"


class GameWriteConflictError(RuntimeError):
    """Raised when another repository instance changed a session first."""


class SqliteGameRepository(InMemoryGameRepository):
    """Persist neutral-fixture sessions as initial seed plus replayable outcomes."""

    def __init__(self, database: Path) -> None:
        super().__init__()
        self._database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    persistence_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        self._load_all()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _payload(session: GameSession) -> str:
        return json.dumps(
            {
                "initial_seed": session.initial_state.seed,
                "current_seed": session.state.seed,
                "outcomes": [event.outcome for event in session.events],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _from_payload(game_id: str, payload_json: str) -> GameSession:
        payload = json.loads(payload_json)
        if set(payload) != {"initial_seed", "current_seed", "outcomes"}:
            raise ValueError("invalid persisted game payload")
        initial_state, batters, pitchers = _neutral_fixture(int(payload["initial_seed"]))
        state, _, _ = _neutral_fixture(int(payload["current_seed"]))
        events: list[GameEvent] = []
        for raw_outcome in payload["outcomes"]:
            before = state
            transition = apply_outcome(before, Outcome(raw_outcome))
            events.append(
                GameEvent(
                    outcome=transition.outcome.value,
                    batter=transition.batter,
                    pitcher=transition.pitcher,
                    runs_scored=transition.runs_scored,
                    inning=before.inning,
                    half=before.half.value,
                    description=_description(
                        transition.outcome.value,
                        transition.batter,
                        transition.runs_scored,
                    ),
                )
            )
            state = transition.state
        return GameSession(game_id, initial_state, state, batters, pitchers, events)

    def _load_all(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT game_id, persistence_version, payload_json FROM games"
            ).fetchall()
        for game_id, version, payload in rows:
            if version != GAME_PERSISTENCE_VERSION:
                continue
            try:
                self._sessions[game_id] = self._from_payload(game_id, payload)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                # Isolate a corrupt save so healthy sessions remain available.
                continue

    def _insert(self, session: GameSession) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO games(game_id, persistence_version, payload_json) VALUES (?, ?, ?)",
                (session.game_id, GAME_PERSISTENCE_VERSION, self._payload(session)),
            )

    def _save_candidate(self, original: GameSession, candidate: GameSession) -> None:
        expected = self._payload(original)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE games
                SET persistence_version=?, payload_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=? AND persistence_version=? AND payload_json=?
                """,
                (
                    GAME_PERSISTENCE_VERSION,
                    self._payload(candidate),
                    candidate.game_id,
                    GAME_PERSISTENCE_VERSION,
                    expected,
                ),
            )
            if cursor.rowcount != 1:
                raise GameWriteConflictError(candidate.game_id)

    def _candidate_mutation(
        self,
        game_id: str,
        operation: Callable[[InMemoryGameRepository], GameSession],
    ) -> GameSession:
        original = self.get(game_id)
        candidate_repository = InMemoryGameRepository()
        candidate_repository._sessions[game_id] = self._snapshot(original)
        candidate = operation(candidate_repository)
        self._save_candidate(original, candidate)
        self._sessions[game_id] = self._snapshot(candidate)
        return self._snapshot(candidate)

    def create(self, seed: int) -> GameSession:
        with self._lock:
            game_id = str(uuid4())
            state, batters, pitchers = _neutral_fixture(seed)
            session = GameSession(game_id, state, state, batters, pitchers, [])
            self._insert(session)
            self._sessions[game_id] = self._snapshot(session)
            return self._snapshot(session)

    def next_pa(self, game_id: str) -> GameSession:
        with self._lock:
            return self._candidate_mutation(game_id, lambda repository: repository.next_pa(game_id))

    def simulate_half(self, game_id: str, max_pa: int = 100) -> GameSession:
        with self._lock:
            return self._candidate_mutation(
                game_id, lambda repository: repository.simulate_half(game_id, max_pa)
            )

    def simulate_full(self, game_id: str, max_pa: int = 1_000) -> GameSession:
        with self._lock:
            return self._candidate_mutation(
                game_id, lambda repository: repository.simulate_full(game_id, max_pa)
            )

    def reset(self, game_id: str, seed: int | None = None) -> GameSession:
        with self._lock:
            return self._candidate_mutation(
                game_id, lambda repository: repository.reset(game_id, seed)
            )
