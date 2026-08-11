"""Fail-closed loader for the three-file rating-snapshot-v0.2 artifact."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .cards import (
    AbilityRating,
    BatSide,
    CardCatalog,
    CardKind,
    PitcherRole,
    PlayerSeasonCard,
    ThrowSide,
)

RATING_ARTIFACT_SCHEMA = "rating-snapshot-v0.2"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _read_verified_csv(
    root: Path, metadata: Mapping[str, object], expected_name: str
) -> list[dict[str, str]]:
    if str(metadata.get("path")) != expected_name:
        raise ValueError(f"manifest path for {expected_name} is invalid")
    path = root / expected_name
    payload = path.read_bytes()
    if _sha256(payload) != str(metadata.get("sha256")):
        raise ValueError(f"artifact fingerprint mismatch: {expected_name}")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != int(str(metadata.get("rows"))):
        raise ValueError(f"artifact row count mismatch: {expected_name}")
    return rows


def _strict_bool(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError("IncompleteSeason must be True or False")


def _ability(row: Mapping[str, str], name: str) -> AbilityRating:
    return AbilityRating(float(row[f"{name}Score"]), float(row[f"{name}RatingRaw"]))


def _card_id(
    kind: CardKind, player_id: str, year: int, model: str, mapping: str
) -> str:
    return f"{kind.value}:{player_id}:{year}:{model}:{mapping}"


def load_card_catalog(root: Path) -> CardCatalog:
    """Load and fingerprint the manifest plus batter, pitcher, and profile CSVs."""
    manifest_path = root / "manifest.json"
    manifest_payload = manifest_path.read_bytes()
    manifest = _object(json.loads(manifest_payload), "manifest")
    if manifest.get("schema_version") != RATING_ARTIFACT_SCHEMA:
        raise ValueError("unsupported rating artifact schema")
    outputs = _object(manifest.get("outputs"), "manifest outputs")
    batter_meta = _object(outputs.get("batter"), "batter output")
    pitcher_meta = _object(outputs.get("pitcher"), "pitcher output")
    profile_meta = _object(outputs.get("player_profiles"), "profile output")
    batter_rows = _read_verified_csv(
        root, batter_meta, "batter_season_ratings.csv"
    )
    pitcher_rows = _read_verified_csv(
        root, pitcher_meta, "pitcher_season_ratings.csv"
    )
    profile_rows = _read_verified_csv(root, profile_meta, "player_profiles.csv")
    profile_version = str(profile_meta.get("version"))
    profiles: dict[str, dict[str, str]] = {}
    for row in profile_rows:
        player_id = row["PlayerID"]
        if player_id in profiles:
            raise ValueError("player profile PlayerID must be unique")
        if row["ProfileVersion"] != profile_version:
            raise ValueError("player profile version does not match manifest")
        profiles[player_id] = row

    models = _object(manifest.get("models"), "manifest models")
    mapping_version = str(manifest.get("mapping_version"))
    cards: list[PlayerSeasonCard] = []
    for kind, rows, ability_names in (
        (CardKind.BATTER, batter_rows, ("Contact", "Power", "Eye", "SpeedProxy")),
        (
            CardKind.PITCHER,
            pitcher_rows,
            ("Stuff", "Control", "HRSuppression", "Stamina"),
        ),
    ):
        for row in rows:
            player_id = row["PlayerID"]
            try:
                profile = profiles[player_id]
            except KeyError as error:
                raise ValueError(f"rating card has no player profile: {player_id}") from error
            if row["PlayerName"] != profile["PlayerName"]:
                raise ValueError(f"rating/profile player name mismatch: {player_id}")
            expected_model = str(models[kind.value])
            if row["ModelVersion"] != expected_model or row["MappingVersion"] != mapping_version:
                raise ValueError("rating row versions do not match manifest")
            year = int(row["SeasonYear"])
            role = None
            if kind is CardKind.PITCHER:
                role = PitcherRole(row["Role"])
            cards.append(
                PlayerSeasonCard(
                    card_id=_card_id(kind, player_id, year, expected_model, mapping_version),
                    player_id=player_id,
                    player_name=row["PlayerName"],
                    season_year=year,
                    team=row["Team"],
                    kind=kind,
                    model_version=expected_model,
                    mapping_version=mapping_version,
                    profile_positions=(profile["ProfilePosition"],),
                    bats=BatSide(profile["Bats"]),
                    throws=ThrowSide(profile["Throws"]),
                    abilities={name: _ability(row, name) for name in ability_names},
                    incomplete_season=_strict_bool(row["IncompleteSeason"]),
                    pitcher_role=role,
                )
            )
    manifest_hash = _sha256(manifest_payload)
    return CardCatalog(f"{RATING_ARTIFACT_SCHEMA}:{manifest_hash}", cards)
