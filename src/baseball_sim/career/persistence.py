"""Schema-versioned JSON persistence with atomic local replacement."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast

from baseball_sim.game.state import GameState, HalfInning, Team
from baseball_sim.simulation.outcomes import Outcome

from .models import (
    CAREER_SCHEMA_VERSION,
    ActiveCareerGame,
    BatterArchetype,
    BatterSkill,
    BatterSkillScores,
    BattingStats,
    CareerEvent,
    CareerOrigin,
    CareerRetiredEvent,
    CareerState,
    GamePlayedEvent,
    Handedness,
    PlateAppearancePlayedEvent,
    PlayerProfile,
    RatingImprovedEvent,
    SeasonAdvancedEvent,
    SeasonRecord,
    initial_state,
)

SAVE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CareerSaveError(RuntimeError):
    """Raised for missing, malformed or unsupported career saves."""


class CareerSaveRepository(Protocol):
    def save(self, save_id: str, state: CareerState) -> Path: ...

    def load(self, save_id: str) -> CareerState: ...


def _scores(value: BatterSkillScores) -> dict[str, float]:
    return {
        "contact": value.contact,
        "power": value.power,
        "eye": value.eye,
        "speed_proxy": value.speed_proxy,
    }


def _stats(value: BattingStats) -> dict[str, int]:
    return {field: getattr(value, field) for field in value.__dataclass_fields__}


def _event(value: CareerEvent) -> dict[str, object]:
    if isinstance(value, PlateAppearancePlayedEvent):
        return {
            "kind": value.kind,
            "season_year": value.season_year,
            "game_number": value.game_number,
            "pa_index": value.pa_index,
            "outcome": value.outcome.value,
            "batter": value.batter,
            "pitcher": value.pitcher,
            "career_plate_appearance": value.career_plate_appearance,
            "development_points_earned": value.development_points_earned,
            "development_points_expired": value.development_points_expired,
        }
    if isinstance(value, GamePlayedEvent):
        return {
            "kind": value.kind,
            "season_year": value.season_year,
            "game_number": value.game_number,
            "plate_appearances": value.plate_appearances,
            "outcomes": [outcome.value for outcome in value.outcomes],
            "xp_earned": value.xp_earned,
            "development_points_earned": value.development_points_earned,
        }
    if isinstance(value, RatingImprovedEvent):
        return {
            "kind": value.kind,
            "skill": value.skill.value,
            "purchases": value.purchases,
            "points_spent": value.points_spent,
            "score_before": value.score_before,
            "score_after": value.score_after,
        }
    if isinstance(value, SeasonAdvancedEvent):
        return {
            "kind": value.kind,
            "previous_year": value.previous_year,
            "next_year": value.next_year,
            "new_age": value.new_age,
        }
    return {
        "kind": value.kind,
        "season_year": value.season_year,
        "age": value.age,
    }


def _game_state(value: GameState) -> dict[str, object]:
    return {
        "away_lineup": list(value.away_lineup),
        "home_lineup": list(value.home_lineup),
        "away_pitcher": value.away_pitcher,
        "home_pitcher": value.home_pitcher,
        "seed": value.seed,
        "rules_version": value.rules_version,
        "simulation_model_version": value.simulation_model_version,
        "rating_snapshot_version": value.rating_snapshot_version,
        "inning": value.inning,
        "half": value.half.value,
        "outs": value.outs,
        "bases": list(value.bases),
        "away_score": value.away_score,
        "home_score": value.home_score,
        "away_lineup_index": value.away_lineup_index,
        "home_lineup_index": value.home_lineup_index,
        "plate_appearances": value.plate_appearances,
        "finished": value.finished,
        "winner": None if value.winner is None else value.winner.value,
    }


def career_to_dict(state: CareerState) -> dict[str, object]:
    profile = state.origin.profile
    return {
        "schema_version": CAREER_SCHEMA_VERSION,
        "model_version": state.model_version,
        "origin": {
            "profile": {
                "player_id": profile.player_id,
                "name": profile.name,
                "position": profile.position,
                "bats": profile.bats.value,
                "throws": profile.throws.value,
                "archetype": profile.archetype.value,
            },
            "starting_age": state.origin.starting_age,
            "starting_season_year": state.origin.starting_season_year,
            "starting_scores": _scores(state.origin.starting_scores),
            "potential_scores": _scores(state.origin.potential_scores),
            "seed": state.origin.seed,
            "season_games": state.origin.season_games,
        },
        "state": {
            "age": state.age,
            "season_year": state.season_year,
            "games_played": state.games_played,
            "experience": state.experience,
            "development_points": state.development_points,
            "expired_development_points": state.expired_development_points,
            "scores": _scores(state.scores),
            "season_purchases": state.season_purchases,
            "season_skill_purchases": list(state.season_skill_purchases),
            "active_game": None
            if state.active_game is None
            else {
                "season_year": state.active_game.season_year,
                "game_number": state.active_game.game_number,
                "game_state": _game_state(state.active_game.game_state),
                "career_outcomes": [
                    outcome.value for outcome in state.active_game.career_outcomes
                ],
            },
            "season_stats": _stats(state.season_stats),
            "career_stats": _stats(state.career_stats),
            "completed_seasons": [
                {
                    "season_year": record.season_year,
                    "age": record.age,
                    "scores_at_end": _scores(record.scores_at_end),
                    "stats": _stats(record.stats),
                }
                for record in state.completed_seasons
            ],
            "events": [_event(event) for event in state.events],
        },
    }


def _as_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CareerSaveError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def _load_scores(value: object) -> BatterSkillScores:
    data = _as_dict(value, "scores")
    return BatterSkillScores(
        float(data["contact"]),
        float(data["power"]),
        float(data["eye"]),
        float(data["speed_proxy"]),
    )


def _load_stats(value: object) -> BattingStats:
    data = _as_dict(value, "stats")
    return BattingStats(**{field: int(data[field]) for field in BattingStats.__dataclass_fields__})


def _load_purchase_counters(value: object) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CareerSaveError("season skill purchase counters must contain four values")
    return cast(tuple[int, int, int, int], tuple(int(item) for item in value))


def _load_event(value: object) -> CareerEvent:
    data = _as_dict(value, "event")
    kind = str(data["kind"])
    if kind == "plate_appearance_played":
        return PlateAppearancePlayedEvent(
            int(data["season_year"]),
            int(data["game_number"]),
            int(data["pa_index"]),
            Outcome(str(data["outcome"])),
            str(data["batter"]),
            str(data["pitcher"]),
            bool(data["career_plate_appearance"]),
            int(data["development_points_earned"]),
            int(data["development_points_expired"]),
        )
    if kind == "game_played":
        outcomes = data["outcomes"]
        if not isinstance(outcomes, list):
            raise CareerSaveError("event outcomes must be an array")
        return GamePlayedEvent(
            int(data["season_year"]),
            int(data["game_number"]),
            int(data["plate_appearances"]),
            tuple(Outcome(str(outcome)) for outcome in outcomes),
            int(data["xp_earned"]),
            int(data["development_points_earned"]),
        )
    if kind == "rating_improved":
        return RatingImprovedEvent(
            BatterSkill(str(data["skill"])),
            int(data["purchases"]),
            int(data["points_spent"]),
            float(data["score_before"]),
            float(data["score_after"]),
        )
    if kind == "season_advanced":
        return SeasonAdvancedEvent(
            int(data["previous_year"]), int(data["next_year"]), int(data["new_age"])
        )
    if kind == "career_retired":
        return CareerRetiredEvent(int(data["season_year"]), int(data["age"]))
    raise CareerSaveError(f"unknown event kind: {kind}")


def _load_game_state(value: object) -> GameState:
    data = _as_dict(value, "game state")
    away = data["away_lineup"]
    home = data["home_lineup"]
    bases = data["bases"]
    if not isinstance(away, list) or not isinstance(home, list) or not isinstance(bases, list):
        raise CareerSaveError("game lineups and bases must be arrays")
    winner_raw = data["winner"]
    return GameState(
        away_lineup=tuple(str(item) for item in away),
        home_lineup=tuple(str(item) for item in home),
        away_pitcher=str(data["away_pitcher"]),
        home_pitcher=str(data["home_pitcher"]),
        seed=int(data["seed"]),
        rules_version=str(data["rules_version"]),
        simulation_model_version=str(data["simulation_model_version"]),
        rating_snapshot_version=str(data["rating_snapshot_version"]),
        inning=int(data["inning"]),
        half=HalfInning(str(data["half"])),
        outs=int(data["outs"]),
        bases=cast(tuple[str | None, str | None, str | None], tuple(bases)),
        away_score=int(data["away_score"]),
        home_score=int(data["home_score"]),
        away_lineup_index=int(data["away_lineup_index"]),
        home_lineup_index=int(data["home_lineup_index"]),
        plate_appearances=int(data["plate_appearances"]),
        finished=bool(data["finished"]),
        winner=None if winner_raw is None else Team(str(winner_raw)),
    )


def career_from_dict(value: object) -> CareerState:
    try:
        root = _as_dict(value, "save")
        if int(root["schema_version"]) != CAREER_SCHEMA_VERSION:
            raise CareerSaveError("unsupported career save schema version")
        origin_data = _as_dict(root["origin"], "origin")
        profile_data = _as_dict(origin_data["profile"], "profile")
        origin = CareerOrigin(
            profile=PlayerProfile(
                str(profile_data["player_id"]),
                str(profile_data["name"]),
                str(profile_data["position"]),
                Handedness(str(profile_data["bats"])),
                Handedness(str(profile_data["throws"])),
                BatterArchetype(str(profile_data["archetype"])),
            ),
            starting_age=int(origin_data["starting_age"]),
            starting_season_year=int(origin_data["starting_season_year"]),
            starting_scores=_load_scores(origin_data["starting_scores"]),
            potential_scores=_load_scores(origin_data["potential_scores"]),
            seed=int(origin_data["seed"]),
            season_games=int(origin_data["season_games"]),
        )
        data = _as_dict(root["state"], "state")
        active_raw = data["active_game"]
        active_game: ActiveCareerGame | None = None
        if active_raw is not None:
            active_data = _as_dict(active_raw, "active game")
            active_outcomes = active_data["career_outcomes"]
            if not isinstance(active_outcomes, list):
                raise CareerSaveError("active game outcomes must be an array")
            active_game = ActiveCareerGame(
                int(active_data["season_year"]),
                int(active_data["game_number"]),
                _load_game_state(active_data["game_state"]),
                tuple(Outcome(str(outcome)) for outcome in active_outcomes),
            )
        records_raw = data["completed_seasons"]
        events_raw = data["events"]
        if not isinstance(records_raw, list) or not isinstance(events_raw, list):
            raise CareerSaveError("records and events must be arrays")
        records = tuple(
            SeasonRecord(
                int(item_data["season_year"]),
                int(item_data["age"]),
                _load_scores(item_data["scores_at_end"]),
                _load_stats(item_data["stats"]),
            )
            for item in records_raw
            for item_data in [_as_dict(item, "season record")]
        )
        state = CareerState(
            origin=origin,
            age=int(data["age"]),
            season_year=int(data["season_year"]),
            games_played=int(data["games_played"]),
            experience=int(data["experience"]),
            development_points=int(data["development_points"]),
            expired_development_points=int(data["expired_development_points"]),
            scores=_load_scores(data["scores"]),
            season_purchases=int(data["season_purchases"]),
            season_skill_purchases=_load_purchase_counters(data["season_skill_purchases"]),
            active_game=active_game,
            season_stats=_load_stats(data["season_stats"]),
            career_stats=_load_stats(data["career_stats"]),
            completed_seasons=records,
            events=tuple(_load_event(item) for item in events_raw),
            schema_version=int(root["schema_version"]),
            model_version=str(root["model_version"]),
        )
        # A save is authoritative only when its materialized state is exactly reproducible
        # from its immutable origin and versioned event stream.
        from .simulation import replay_career

        if replay_career(initial_state(origin), state.events) != state:
            raise CareerSaveError("career state does not match its event log")
        return state
    except CareerSaveError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise CareerSaveError("career save is malformed") from error


class AtomicJsonCareerRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, save_id: str) -> Path:
        if not SAVE_ID.fullmatch(save_id):
            raise ValueError("save_id may contain only letters, digits, underscore and hyphen")
        return self.root / f"{save_id}.json"

    def save(self, save_id: str, state: CareerState) -> Path:
        path = self._path(save_id)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            career_to_dict(state), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.root,
                prefix=f".{save_id}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return path

    def load(self, save_id: str) -> CareerState:
        path = self._path(save_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CareerSaveError("career save was not found") from error
        except (OSError, json.JSONDecodeError) as error:
            raise CareerSaveError("career save could not be read") from error
        return career_from_dict(payload)
