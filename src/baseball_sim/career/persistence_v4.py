"""Canonical JSON codec and SQLite CAS repository for Career v4 aggregates."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .aggregate_v4 import CareerAggregateV4
from .calendar_v4 import PlannedAction, Weekday, build_career_calendar, plan_week
from .condition import CareerCondition, Injury, InjurySeverity
from .lifecycle_v4 import CareerLifecycle, CareerPhase
from .persistence import career_from_dict, career_to_dict
from .team_status import TeamStanding, TeamStatus
from .weekly import WeeklyAction, WeeklyDevelopment

CAREER_V4_PERSISTENCE_VERSION = "career-sqlite-v4"


class CareerV4NotFoundError(LookupError):
    pass


class CareerV4ConflictError(RuntimeError):
    pass


class CareerV4CorruptError(RuntimeError):
    pass


class CareerV4ValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CareerV4Record:
    career_id: str
    revision: int
    aggregate: CareerAggregateV4
    autosaved_at: str
    persistence_version: str = CAREER_V4_PERSISTENCE_VERSION


def aggregate_to_dict(value: CareerAggregateV4) -> dict[str, object]:
    injury = value.condition.injury
    plan = value.current_plan
    development = {
        field.name: getattr(value.weekly_development, field.name)
        for field in fields(WeeklyDevelopment)
    }
    return {
        "schema_version": value.schema_version,
        "model_version": value.model_version,
        "migrated_from_schema": value.migrated_from_schema,
        "career": career_to_dict(value.career),
        "calendar": {
            "team_id": value.calendar.team_id,
            "seed": value.calendar.seed,
            "opponent_ids": list(value.calendar.opponent_ids),
            "model_version": value.calendar.model_version,
        },
        "lifecycle": {
            "season_number": value.lifecycle.season_number,
            "week": value.lifecycle.week,
            "weekday": value.lifecycle.weekday,
            "phase": value.lifecycle.phase.value,
            "model_version": value.lifecycle.model_version,
        },
        "weekly_development": development,
        "condition": {
            "fatigue": value.condition.fatigue,
            "form_latent": value.condition.form_latent,
            "injury": None
            if injury is None
            else {"severity": injury.severity.value, "days_remaining": injury.days_remaining},
        },
        "team_standing": {
            "coach_trust": value.team_standing.coach_trust,
            "status": value.team_standing.status.value,
            "promotion_weeks": value.team_standing.promotion_weeks,
            "demotion_weeks": value.team_standing.demotion_weeks,
        },
        "current_plan": None
        if plan is None
        else {
            "week": plan.week,
            "actions": [
                {"weekday": int(item.weekday), "action": item.action.value}
                for item in plan.actions
            ],
            "action_points_used": plan.action_points_used,
            "action_points_available": plan.action_points_available,
            "model_version": plan.model_version,
        },
    }


def aggregate_from_dict(value: object) -> CareerAggregateV4:
    try:
        if not isinstance(value, dict):
            raise TypeError("aggregate payload must be an object")
        calendar_data = value["calendar"]
        lifecycle_data = value["lifecycle"]
        condition_data = value["condition"]
        standing_data = value["team_standing"]
        development_data = value["weekly_development"]
        if not all(
            isinstance(item, dict)
            for item in (
                calendar_data,
                lifecycle_data,
                condition_data,
                standing_data,
                development_data,
            )
        ):
            raise TypeError("aggregate components must be objects")
        calendar = build_career_calendar(
            team_id=str(calendar_data["team_id"]),
            seed=int(calendar_data["seed"]),
            opponent_ids=tuple(str(item) for item in calendar_data["opponent_ids"]),
        )
        lifecycle = CareerLifecycle(
            season_number=int(lifecycle_data["season_number"]),
            week=int(lifecycle_data["week"]),
            weekday=int(lifecycle_data["weekday"]),
            phase=CareerPhase(str(lifecycle_data["phase"])),
            model_version=str(lifecycle_data["model_version"]),
        )
        injury_data = condition_data["injury"]
        injury = None
        if injury_data is not None:
            if not isinstance(injury_data, dict):
                raise TypeError("injury must be an object")
            injury = Injury(
                InjurySeverity(str(injury_data["severity"])),
                int(injury_data["days_remaining"]),
            )
        condition = CareerCondition(
            float(condition_data["fatigue"]),
            float(condition_data["form_latent"]),
            injury,
        )
        standing = TeamStanding(
            float(standing_data["coach_trust"]),
            TeamStatus(str(standing_data["status"])),
            int(standing_data["promotion_weeks"]),
            int(standing_data["demotion_weeks"]),
        )
        development = WeeklyDevelopment(
            **{
                field.name: development_data[field.name]
                for field in fields(WeeklyDevelopment)
            }
        )
        plan_data = value["current_plan"]
        plan = None
        if plan_data is not None:
            if not isinstance(plan_data, dict):
                raise TypeError("current_plan must be an object")
            actions = tuple(
                PlannedAction(Weekday(int(item["weekday"])), WeeklyAction(str(item["action"])))
                for item in plan_data["actions"]
            )
            plan = plan_week(calendar, int(plan_data["week"]), actions)
            if plan.action_points_used != int(plan_data["action_points_used"]):
                raise ValueError("saved action point total is invalid")
        return CareerAggregateV4(
            career=career_from_dict(value["career"]),
            calendar=calendar,
            lifecycle=lifecycle,
            weekly_development=development,
            condition=condition,
            team_standing=standing,
            current_plan=plan,
            migrated_from_schema=(
                None
                if value["migrated_from_schema"] is None
                else int(value["migrated_from_schema"])
            ),
            schema_version=int(value["schema_version"]),
            model_version=str(value["model_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CareerV4CorruptError("Career v4 save is malformed or incompatible") from error


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _valid_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise CareerV4ValidationError("career_id must be a canonical UUID") from error
    if str(parsed) != value:
        raise CareerV4ValidationError("career_id must be a canonical UUID")
    return value


class SqliteCareerV4Repository:
    """Separate v4 tables with atomic revision CAS and a compact operation ledger."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS careers_v4 (
                    career_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL, autosaved_at TEXT NOT NULL,
                    persistence_version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS career_v4_operations (
                    operation_id TEXT PRIMARY KEY, career_id TEXT NOT NULL,
                    action TEXT NOT NULL, request_hash TEXT NOT NULL,
                    result_revision INTEGER NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _decode(self, row: sqlite3.Row) -> CareerV4Record:
        if str(row["persistence_version"]) != CAREER_V4_PERSISTENCE_VERSION:
            raise CareerV4CorruptError("Career v4 persistence version is unsupported")
        try:
            aggregate = aggregate_from_dict(json.loads(str(row["state_json"])))
        except (json.JSONDecodeError, CareerV4CorruptError) as error:
            raise CareerV4CorruptError("Career v4 save is corrupt") from error
        return CareerV4Record(
            str(row["career_id"]), int(row["revision"]), aggregate, str(row["autosaved_at"])
        )

    def get(self, career_id: str) -> CareerV4Record:
        career_id = _valid_id(career_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM careers_v4 WHERE career_id=?", (career_id,)
            ).fetchone()
            if row is None:
                raise CareerV4NotFoundError(career_id)
            return self._decode(row)

    def list(self) -> list[CareerV4Record]:
        """Return valid saves newest-first while isolating corrupt rows."""
        records: list[CareerV4Record] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM careers_v4 ORDER BY autosaved_at DESC"
            ).fetchall()
            for row in rows:
                try:
                    records.append(self._decode(row))
                except CareerV4CorruptError:
                    continue
        return records

    def _duplicate(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        career_id: str | None,
        action: str,
        request_hash: str,
    ) -> CareerV4Record:
        if (
            (career_id is not None and str(row["career_id"]) != career_id)
            or str(row["action"]) != action
            or str(row["request_hash"]) != request_hash
        ):
            raise CareerV4ConflictError("operation_id was reused with a different request")
        current = connection.execute(
            "SELECT * FROM careers_v4 WHERE career_id=?", (str(row["career_id"]),)
        ).fetchone()
        if current is None:
            raise CareerV4NotFoundError(str(row["career_id"]))
        return self._decode(current)

    def create(
        self,
        *,
        operation_id: str,
        expected_revision: int,
        request_payload: object,
        aggregate_factory: Callable[[str], CareerAggregateV4],
        career_id: str | None = None,
        action: str = "create",
    ) -> CareerV4Record:
        if expected_revision != 0:
            raise CareerV4ConflictError("new Career v4 saves require expected_revision=0")
        request_hash = _fingerprint(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM career_v4_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if duplicate is not None:
                return self._duplicate(
                    connection,
                    duplicate,
                    career_id=career_id,
                    action=action,
                    request_hash=request_hash,
                )
            identifier = _valid_id(career_id) if career_id is not None else str(uuid4())
            if connection.execute(
                "SELECT 1 FROM careers_v4 WHERE career_id=?", (identifier,)
            ).fetchone():
                raise CareerV4ConflictError("Career v4 save already exists")
            try:
                aggregate = aggregate_factory(identifier)
            except ValueError as error:
                raise CareerV4ValidationError(str(error)) from error
            timestamp = _now()
            connection.execute(
                "INSERT INTO careers_v4 VALUES (?,1,?,?,?)",
                (
                    identifier,
                    _canonical(aggregate_to_dict(aggregate)),
                    timestamp,
                    CAREER_V4_PERSISTENCE_VERSION,
                ),
            )
            connection.execute(
                "INSERT INTO career_v4_operations VALUES (?,?,?,?,1)",
                (operation_id, identifier, action, request_hash),
            )
            return CareerV4Record(identifier, 1, aggregate, timestamp)

    def mutate(
        self,
        *,
        career_id: str,
        operation_id: str,
        action: str,
        expected_revision: int,
        request_payload: object,
        operation: Callable[[CareerAggregateV4], CareerAggregateV4],
    ) -> CareerV4Record:
        career_id = _valid_id(career_id)
        request_hash = _fingerprint(request_payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM career_v4_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if duplicate is not None:
                return self._duplicate(
                    connection,
                    duplicate,
                    career_id=career_id,
                    action=action,
                    request_hash=request_hash,
                )
            row = connection.execute(
                "SELECT * FROM careers_v4 WHERE career_id=?", (career_id,)
            ).fetchone()
            if row is None:
                raise CareerV4NotFoundError(career_id)
            current = self._decode(row)
            if current.revision != expected_revision:
                raise CareerV4ConflictError(
                    f"expected revision {expected_revision}, current is {current.revision}"
                )
            try:
                aggregate = operation(current.aggregate)
            except ValueError as error:
                raise CareerV4ValidationError(str(error)) from error
            revision = current.revision + 1
            timestamp = _now()
            connection.execute(
                "UPDATE careers_v4 SET revision=?,state_json=?,autosaved_at=? WHERE career_id=?",
                (revision, _canonical(aggregate_to_dict(aggregate)), timestamp, career_id),
            )
            connection.execute(
                "INSERT INTO career_v4_operations VALUES (?,?,?,?,?)",
                (operation_id, career_id, action, request_hash, revision),
            )
            return CareerV4Record(career_id, revision, aggregate, timestamp)
