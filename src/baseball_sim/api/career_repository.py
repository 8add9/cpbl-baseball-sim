"""Durable optimistic career sessions backed by the Python standard library SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from baseball_sim.career.models import CareerState
from baseball_sim.career.persistence import career_from_dict, career_to_dict

CAREER_API_PERSISTENCE_VERSION = "career-sqlite-v1"
StateOperation = Callable[[CareerState], CareerState]


class CareerNotFoundError(LookupError):
    pass


class CareerRevisionConflictError(RuntimeError):
    pass


class CareerOperationConflictError(RuntimeError):
    pass


class CareerCorruptError(RuntimeError):
    pass


class CareerValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CareerRecord:
    career_id: str
    revision: int
    state: CareerState
    autosaved_at: str
    persistence_version: str = CAREER_API_PERSISTENCE_VERSION


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _state_json(state: CareerState) -> str:
    return _canonical(career_to_dict(state))


def _validate_career_id(career_id: str) -> str:
    try:
        parsed = UUID(career_id)
    except ValueError as error:
        raise CareerValidationError("career_id must be a canonical UUID") from error
    if str(parsed) != career_id:
        raise CareerValidationError("career_id must be a canonical UUID")
    return career_id


class SqliteCareerRepository:
    """Atomic revisioned storage with a compact idempotency ledger per operation id."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS careers (
                    career_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    state_json TEXT NOT NULL,
                    autosaved_at TEXT NOT NULL,
                    persistence_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS career_operations_v2 (
                    operation_id TEXT PRIMARY KEY,
                    career_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    result_revision INTEGER NOT NULL,
                    result_autosaved_at TEXT NOT NULL,
                    persistence_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_career_operations_v2_career
                    ON career_operations_v2(career_id);
                """
            )

    @staticmethod
    def _decode(
        career_id: str,
        revision: int,
        state_json: str,
        autosaved_at: str,
        persistence_version: str,
    ) -> CareerRecord:
        try:
            payload = json.loads(state_json)
            state = career_from_dict(payload)
        except Exception as error:
            raise CareerCorruptError("career save is corrupt or incompatible") from error
        if persistence_version != CAREER_API_PERSISTENCE_VERSION:
            raise CareerCorruptError("career persistence version is unsupported")
        return CareerRecord(career_id, revision, state, autosaved_at, persistence_version)

    def _operation_result(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        career_id: str | None,
        action: str,
        request_hash: str,
    ) -> CareerRecord:
        if (
            (career_id is not None and str(row["career_id"]) != career_id)
            or str(row["action"]) != action
            or str(row["request_hash"]) != request_hash
        ):
            raise CareerOperationConflictError(
                "operation_id was already used with a different request"
            )
        current = connection.execute(
            "SELECT * FROM careers WHERE career_id=?", (str(row["career_id"]),)
        ).fetchone()
        if current is None:
            raise CareerNotFoundError(str(row["career_id"]))
        return self._decode(
            str(current["career_id"]),
            int(current["revision"]),
            str(current["state_json"]),
            str(current["autosaved_at"]),
            str(current["persistence_version"]),
        )

    def create(
        self,
        *,
        operation_id: str,
        expected_revision: int,
        request_payload: object,
        state_factory: Callable[[str], CareerState],
    ) -> CareerRecord:
        if expected_revision != 0:
            raise CareerRevisionConflictError("new careers require expected_revision=0")
        request_hash = _fingerprint(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM career_operations_v2 WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing is not None:
                return self._operation_result(
                    connection,
                    existing,
                    career_id=None,
                    action="create",
                    request_hash=request_hash,
                )
            career_id = str(uuid4())
            try:
                state = state_factory(career_id)
            except ValueError as error:
                raise CareerValidationError(str(error)) from error
            timestamp = _now()
            serialized = _state_json(state)
            connection.execute(
                "INSERT INTO careers VALUES (?, ?, ?, ?, ?)",
                (career_id, 1, serialized, timestamp, CAREER_API_PERSISTENCE_VERSION),
            )
            connection.execute(
                "INSERT INTO career_operations_v2 VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    operation_id,
                    career_id,
                    "create",
                    request_hash,
                    1,
                    timestamp,
                    CAREER_API_PERSISTENCE_VERSION,
                ),
            )
            return CareerRecord(career_id, 1, state, timestamp)

    def get(self, career_id: str) -> CareerRecord:
        career_id = _validate_career_id(career_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM careers WHERE career_id=?", (career_id,)
            ).fetchone()
            if row is None:
                raise CareerNotFoundError(career_id)
            return self._decode(
                career_id,
                int(row["revision"]),
                str(row["state_json"]),
                str(row["autosaved_at"]),
                str(row["persistence_version"]),
            )

    def list(self) -> list[CareerRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM careers ORDER BY autosaved_at DESC, career_id"
            ).fetchall()
            records: list[CareerRecord] = []
            for row in rows:
                try:
                    records.append(
                        self._decode(
                            str(row["career_id"]),
                            int(row["revision"]),
                            str(row["state_json"]),
                            str(row["autosaved_at"]),
                            str(row["persistence_version"]),
                        )
                    )
                except CareerCorruptError:
                    continue
            return records

    def mutate(
        self,
        *,
        career_id: str,
        operation_id: str,
        action: str,
        expected_revision: int,
        request_payload: object,
        operation: StateOperation,
    ) -> CareerRecord:
        career_id = _validate_career_id(career_id)
        request_hash = _fingerprint(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT * FROM career_operations_v2 WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if previous is not None:
                return self._operation_result(
                    connection,
                    previous,
                    career_id=career_id,
                    action=action,
                    request_hash=request_hash,
                )
            row = connection.execute(
                "SELECT * FROM careers WHERE career_id=?", (career_id,)
            ).fetchone()
            if row is None:
                raise CareerNotFoundError(career_id)
            current_revision = int(row["revision"])
            if expected_revision != current_revision:
                raise CareerRevisionConflictError(
                    f"expected revision {expected_revision}, current revision is {current_revision}"
                )
            current = self._decode(
                career_id,
                current_revision,
                str(row["state_json"]),
                str(row["autosaved_at"]),
                str(row["persistence_version"]),
            )
            try:
                state = operation(current.state)
            except ValueError as error:
                raise CareerValidationError(str(error)) from error
            revision = current_revision + 1
            timestamp = _now()
            serialized = _state_json(state)
            connection.execute(
                """UPDATE careers
                   SET revision=?, state_json=?, autosaved_at=?, persistence_version=?
                   WHERE career_id=?""",
                (
                    revision,
                    serialized,
                    timestamp,
                    CAREER_API_PERSISTENCE_VERSION,
                    career_id,
                ),
            )
            connection.execute(
                "INSERT INTO career_operations_v2 VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    operation_id,
                    career_id,
                    action,
                    request_hash,
                    revision,
                    timestamp,
                    CAREER_API_PERSISTENCE_VERSION,
                ),
            )
            return CareerRecord(career_id, revision, state, timestamp)
