"""Separate SQLite persistence for revisioned Manager leagues."""

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

from baseball_sim.manager.cards import CardCatalog
from baseball_sim.manager.league import ManagerLeagueState
from baseball_sim.manager.loader import load_card_catalog
from baseball_sim.manager.persistence import manager_state_from_dict, manager_state_to_dict

MANAGER_PERSISTENCE_VERSION = "manager-sqlite-v1"
ManagerOperation = Callable[[ManagerLeagueState, CardCatalog], ManagerLeagueState]


class ManagerNotFoundError(LookupError):
    pass


class ManagerRevisionConflictError(RuntimeError):
    pass


class ManagerOperationConflictError(RuntimeError):
    pass


class ManagerCorruptError(RuntimeError):
    pass


class ManagerValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ManagerRecord:
    manager_id: str
    revision: int
    state: ManagerLeagueState
    autosaved_at: str
    persistence_version: str = MANAGER_PERSISTENCE_VERSION


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _manager_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ManagerValidationError("manager_id must be a canonical UUID") from error
    if str(parsed) != value:
        raise ManagerValidationError("manager_id must be a canonical UUID")
    return value


class SqliteManagerRepository:
    def __init__(self, database_path: Path, artifact_root: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.catalog = load_card_catalog(artifact_root)
        except Exception as error:
            raise ManagerCorruptError("rating artifact failed validation") from error
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS manager_leagues (
                    manager_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    state_json TEXT NOT NULL,
                    autosaved_at TEXT NOT NULL,
                    persistence_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS manager_operations (
                    operation_id TEXT PRIMARY KEY,
                    manager_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    result_revision INTEGER NOT NULL,
                    result_autosaved_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_manager_operations_manager
                    ON manager_operations(manager_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _decode(self, row: sqlite3.Row) -> ManagerRecord:
        if str(row["persistence_version"]) != MANAGER_PERSISTENCE_VERSION:
            raise ManagerCorruptError("Manager persistence version is unsupported")
        try:
            state = manager_state_from_dict(json.loads(str(row["state_json"])), self.catalog)
        except Exception as error:
            raise ManagerCorruptError("Manager save is corrupt or incompatible") from error
        return ManagerRecord(
            str(row["manager_id"]),
            int(row["revision"]),
            state,
            str(row["autosaved_at"]),
        )

    def _duplicate(
        self,
        connection: sqlite3.Connection,
        operation: sqlite3.Row,
        *,
        manager_id: str | None,
        action: str,
        request_hash: str,
    ) -> ManagerRecord:
        if (
            (manager_id is not None and str(operation["manager_id"]) != manager_id)
            or str(operation["action"]) != action
            or str(operation["request_hash"]) != request_hash
        ):
            raise ManagerOperationConflictError(
                "operation_id was already used with a different request"
            )
        row = connection.execute(
            "SELECT * FROM manager_leagues WHERE manager_id=?",
            (str(operation["manager_id"]),),
        ).fetchone()
        if row is None:
            raise ManagerNotFoundError(str(operation["manager_id"]))
        return self._decode(row)

    def create(
        self,
        *,
        operation_id: str,
        expected_revision: int,
        request_payload: object,
        state_factory: Callable[[CardCatalog], ManagerLeagueState],
    ) -> ManagerRecord:
        if expected_revision != 0:
            raise ManagerRevisionConflictError("new leagues require expected_revision=0")
        fingerprint = _hash(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM manager_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if duplicate is not None:
                return self._duplicate(
                    connection,
                    duplicate,
                    manager_id=None,
                    action="create",
                    request_hash=fingerprint,
                )
            try:
                state = state_factory(self.catalog)
            except (ValueError, RuntimeError) as error:
                raise ManagerValidationError(str(error)) from error
            manager_id = str(uuid4())
            timestamp = _now()
            connection.execute(
                "INSERT INTO manager_leagues VALUES (?, ?, ?, ?, ?)",
                (
                    manager_id,
                    1,
                    _canonical(manager_state_to_dict(state)),
                    timestamp,
                    MANAGER_PERSISTENCE_VERSION,
                ),
            )
            connection.execute(
                "INSERT INTO manager_operations VALUES (?, ?, ?, ?, ?, ?)",
                (operation_id, manager_id, "create", fingerprint, 1, timestamp),
            )
            return ManagerRecord(manager_id, 1, state, timestamp)

    def get(self, manager_id: str) -> ManagerRecord:
        manager_id = _manager_id(manager_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM manager_leagues WHERE manager_id=?", (manager_id,)
            ).fetchone()
            if row is None:
                raise ManagerNotFoundError(manager_id)
            return self._decode(row)

    def list(self) -> list[ManagerRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM manager_leagues ORDER BY autosaved_at DESC, manager_id"
            ).fetchall()
            records: list[ManagerRecord] = []
            for row in rows:
                try:
                    records.append(self._decode(row))
                except ManagerCorruptError:
                    continue
            return records

    def mutate(
        self,
        *,
        manager_id: str,
        operation_id: str,
        action: str,
        expected_revision: int,
        request_payload: object,
        operation: ManagerOperation,
    ) -> ManagerRecord:
        manager_id = _manager_id(manager_id)
        fingerprint = _hash(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM manager_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if duplicate is not None:
                return self._duplicate(
                    connection,
                    duplicate,
                    manager_id=manager_id,
                    action=action,
                    request_hash=fingerprint,
                )
            row = connection.execute(
                "SELECT * FROM manager_leagues WHERE manager_id=?", (manager_id,)
            ).fetchone()
            if row is None:
                raise ManagerNotFoundError(manager_id)
            record = self._decode(row)
            if record.revision != expected_revision:
                raise ManagerRevisionConflictError(
                    f"expected revision {expected_revision}, current revision is {record.revision}"
                )
            try:
                state = operation(record.state, self.catalog)
            except (ValueError, RuntimeError) as error:
                raise ManagerValidationError(str(error)) from error
            revision = record.revision + 1
            timestamp = _now()
            connection.execute(
                """UPDATE manager_leagues
                   SET revision=?, state_json=?, autosaved_at=?, persistence_version=?
                   WHERE manager_id=?""",
                (
                    revision,
                    _canonical(manager_state_to_dict(state)),
                    timestamp,
                    MANAGER_PERSISTENCE_VERSION,
                    manager_id,
                ),
            )
            connection.execute(
                "INSERT INTO manager_operations VALUES (?, ?, ?, ?, ?, ?)",
                (operation_id, manager_id, action, fingerprint, revision, timestamp),
            )
            return ManagerRecord(manager_id, revision, state, timestamp)
