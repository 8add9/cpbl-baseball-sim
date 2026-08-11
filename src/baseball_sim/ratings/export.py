"""Build deterministic, versioned game rating snapshots from research artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc
from dotenv import dotenv_values

from .mapping import MAPPING_VERSION, rating_display, score_to_rating

SCHEMA_VERSION = "rating-snapshot-v0.1"
ENGINE_VERSION = "rating-engine-v0.1"
BATTER_MODEL_VERSION = "A_WinsorizedBalanced-v0.1"
PITCHER_MODEL_VERSION = "B_Role-v0.1"
AS_OF_DATE = "2026-08-11"
BATTER_ABILITIES = ("Contact", "Power", "Eye", "SpeedProxy")
PITCHER_ABILITIES = ("Stuff", "Control", "HRSuppression", "Stamina")
SOURCE_TABLES = ("Teams", "Players", "BattingStats", "PitchingStats")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_ability_rows(
    frame: pd.DataFrame,
    abilities: Sequence[str],
    key_columns: Sequence[str],
) -> None:
    counts = frame.groupby(list(key_columns), dropna=False)["Ability"].agg(
        Count="size", Unique="nunique"
    )
    expected = len(abilities)
    invalid = counts[(counts.Count != expected) | (counts.Unique != expected)]
    if not invalid.empty:
        raise ValueError(f"player-season ability rows are incomplete or duplicated: {len(invalid)}")
    found = set(frame["Ability"].unique())
    if found != set(abilities):
        raise ValueError(f"unexpected ability set: {sorted(found)}")


def _map_final_ratings(frame: pd.DataFrame) -> pd.DataFrame:
    mapped = frame.copy()
    mapped["RatingRaw"] = mapped["CompositeScore"].map(score_to_rating)
    mapped["RatingDisplay"] = mapped["RatingRaw"].map(rating_display)
    return mapped


def build_batter_snapshot(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "PlayerID",
        "PlayerName",
        "SeasonYear",
        "Team",
        "PA",
        "Ability",
        "CompositeScore",
        "Eligible",
        "Confidence",
        "IncompleteSeason",
        "AsOfDate",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"batter source missing columns: {sorted(missing)}")
    frame = source[source["Eligible"].astype(bool)].copy()
    if frame.empty:
        raise ValueError("batter source has no eligible rows")
    if set(frame.AsOfDate.astype(str)) != {AS_OF_DATE}:
        raise ValueError("batter source AsOfDate does not match frozen contract")
    index = [
        "PlayerID",
        "PlayerName",
        "SeasonYear",
        "Team",
        "PA",
        "Confidence",
        "IncompleteSeason",
        "AsOfDate",
    ]
    _validate_ability_rows(frame, BATTER_ABILITIES, ["PlayerID", "SeasonYear"])
    frame = _map_final_ratings(frame)
    score = frame.pivot(index=index, columns="Ability", values="CompositeScore")
    raw = frame.pivot(index=index, columns="Ability", values="RatingRaw")
    display = frame.pivot(index=index, columns="Ability", values="RatingDisplay")
    score.columns = [f"{name}Score" for name in score.columns]
    raw.columns = [f"{name}RatingRaw" for name in raw.columns]
    display.columns = [f"{name}RatingDisplay" for name in display.columns]
    output = score.join(raw).join(display).reset_index()
    output.insert(4, "ModelVersion", BATTER_MODEL_VERSION)
    output.insert(5, "MappingVersion", MAPPING_VERSION)
    return _finalize(output, BATTER_ABILITIES)


def build_pitcher_snapshot(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "PlayerID",
        "PlayerName",
        "SeasonYear",
        "Team",
        "Role",
        "G",
        "GS",
        "IP",
        "BF",
        "Ability",
        "CompositeScore",
        "Eligible",
        "Confidence",
        "IncompleteSeason",
        "AsOfDate",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"pitcher source missing columns: {sorted(missing)}")
    frame = source[source["Eligible"].astype(bool)].copy()
    if frame.empty:
        raise ValueError("pitcher source has no eligible rows")
    if set(frame.AsOfDate.astype(str)) != {AS_OF_DATE}:
        raise ValueError("pitcher source AsOfDate does not match frozen contract")
    index = [
        "PlayerID",
        "PlayerName",
        "SeasonYear",
        "Team",
        "Role",
        "G",
        "GS",
        "IP",
        "BF",
        "Confidence",
        "IncompleteSeason",
        "AsOfDate",
    ]
    _validate_ability_rows(frame, PITCHER_ABILITIES, ["PlayerID", "SeasonYear"])
    frame = _map_final_ratings(frame)
    score = frame.pivot(index=index, columns="Ability", values="CompositeScore")
    raw = frame.pivot(index=index, columns="Ability", values="RatingRaw")
    display = frame.pivot(index=index, columns="Ability", values="RatingDisplay")
    score.columns = [f"{name}Score" for name in score.columns]
    raw.columns = [f"{name}RatingRaw" for name in raw.columns]
    display.columns = [f"{name}RatingDisplay" for name in display.columns]
    output = score.join(raw).join(display).reset_index()
    output.insert(5, "ModelVersion", PITCHER_MODEL_VERSION)
    output.insert(6, "MappingVersion", MAPPING_VERSION)
    return _finalize(output, PITCHER_ABILITIES)


def _finalize(frame: pd.DataFrame, abilities: Sequence[str]) -> pd.DataFrame:
    for ability in abilities:
        for suffix in ("Score", "RatingRaw", "RatingDisplay"):
            column = f"{ability}{suffix}"
            if column not in frame or frame[column].isna().any():
                raise ValueError(f"eligible rating output contains nulls in {column}")
    keys = ["PlayerID", "SeasonYear", "ModelVersion"]
    if frame.duplicated(keys).any():
        raise ValueError("rating output key is not unique")
    incomplete = frame["SeasonYear"].eq(2026)
    if not frame.loc[incomplete, "IncompleteSeason"].astype(bool).all():
        raise ValueError("all 2026 rows must be incomplete")
    if frame.loc[~incomplete, "IncompleteSeason"].astype(bool).any():
        raise ValueError("completed seasons cannot be incomplete")
    return frame.sort_values(keys, kind="stable").reset_index(drop=True)


def _connect_reader(config: Mapping[str, str | None]) -> pyodbc.Connection:
    driver = config.get("BASEBALL_DATA_DB_DRIVER") or "ODBC Driver 18 for SQL Server"
    server = config.get("BASEBALL_DATA_DB_SERVER") or "127.0.0.1"
    port = config.get("BASEBALL_DATA_DB_PORT") or "1433"
    database = config.get("BASEBALL_DATA_DB_DATABASE") or "BaseballRealData"
    username = config.get("BASEBALL_DATA_DB_USERNAME")
    password = config.get("BASEBALL_DATA_DB_PASSWORD")
    if not username or not password:
        raise ValueError("read-only BaseballRealData credentials are required")
    if username.lower() in {"sa", "dbo"}:
        raise ValueError("administrative SQL identities are forbidden in the game project")
    trust = config.get("BASEBALL_DATA_DB_TRUST_SERVER_CERTIFICATE") or "yes"
    connection_string = (
        f"DRIVER={{{driver}}};SERVER={server},{port};DATABASE={database};"
        f"UID={username};PWD={password};Encrypt=no;TrustServerCertificate={trust}"
    )
    return pyodbc.connect(connection_string, autocommit=False)


def read_source_fingerprint(config: Mapping[str, str | None]) -> dict[str, Any]:
    with _connect_reader(config) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT HAS_PERMS_BY_NAME('dbo.BattingStats','OBJECT','SELECT'), "
            "HAS_PERMS_BY_NAME('dbo.BattingStats','OBJECT','UPDATE')"
        )
        select_permission, update_permission = tuple(cursor.fetchone())
        if select_permission != 1 or update_permission != 0:
            raise PermissionError("SQL identity is not proven SELECT-only")
        tables: dict[str, dict[str, int | None]] = {}
        for table in SOURCE_TABLES:
            cursor.execute(
                f"SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM dbo.[{table}]"
            )
            count, checksum = tuple(cursor.fetchone())
            tables[table] = {
                "rows": int(count),
                "checksum": None if checksum is None else int(checksum),
            }
        connection.rollback()
    return {"database": "BaseballRealData", "identity": "baseball_game_reader", "tables": tables}


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    text = frame.to_csv(index=False, lineterminator="\n", float_format="%.12g")
    return text.encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def export_snapshots(
    data_dir: Path,
    output_dir: Path,
    db_config: Mapping[str, str | None],
) -> dict[str, Any]:
    batter_source = data_dir / "analysis" / "output" / "rating_scale_comparison.csv"
    pitcher_source = data_dir / "analysis" / "output" / "pitching_rating_scale_comparison.csv"
    batter = build_batter_snapshot(pd.read_csv(batter_source, low_memory=False))
    pitcher = build_pitcher_snapshot(pd.read_csv(pitcher_source, low_memory=False))
    batter_payload, pitcher_payload = _csv_bytes(batter), _csv_bytes(pitcher)
    batter_path = output_dir / "batter_season_ratings.csv"
    pitcher_path = output_dir / "pitcher_season_ratings.csv"
    _atomic_write(batter_path, batter_payload)
    _atomic_write(pitcher_path, pitcher_payload)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "as_of_date": AS_OF_DATE,
        "models": {"batter": BATTER_MODEL_VERSION, "pitcher": PITCHER_MODEL_VERSION},
        "mapping_version": MAPPING_VERSION,
        "source_database": read_source_fingerprint(db_config),
        "inputs": {
            "batter_research": {"path": batter_source.name, "sha256": sha256_file(batter_source)},
            "pitcher_research": {
                "path": pitcher_source.name,
                "sha256": sha256_file(pitcher_source),
            },
        },
        "outputs": {
            "batter": {
                "path": batter_path.name,
                "rows": len(batter),
                "sha256": _hash_bytes(batter_payload),
            },
            "pitcher": {
                "path": pitcher_path.name,
                "rows": len(pitcher),
                "sha256": _hash_bytes(pitcher_payload),
            },
        },
        "invariants": {
            "simulation_uses_raw_not_display": True,
            "overall_included": False,
            "season_2026_incomplete": True,
            "season_2026_calibration_reference": False,
        },
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(output_dir / "manifest.json", manifest_payload)
    return manifest


def _load_config(env_path: Path) -> dict[str, str | None]:
    values = dict(dotenv_values(env_path))
    for key, value in os.environ.items():
        if key.startswith("BASEBALL_DATA_"):
            values[key] = value
    return values


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args(list(argv) if argv is not None else None)
    manifest = export_snapshots(args.data_dir, args.output_dir, _load_config(args.env))
    print(json.dumps(manifest["outputs"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
