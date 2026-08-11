from __future__ import annotations

import json
from dataclasses import replace

import pytest

import baseball_sim.career.persistence as persistence_module
from baseball_sim.career import (
    AtomicJsonCareerRepository,
    BatterArchetype,
    BatterSkill,
    CareerSaveError,
    Handedness,
    create_career,
    next_pa,
    replay_career,
    simulate_games,
    spend_development_points,
)


def _progressed():
    state = create_career(
        player_id="save-player",
        name="存檔打者",
        position="1B",
        bats=Handedness.RIGHT,
        throws=Handedness.RIGHT,
        archetype=BatterArchetype.POWER,
        age=18,
        season_year=2026,
        seed=777,
        season_games=16,
    )
    state = simulate_games(state, 15, plate_appearances=6)
    return spend_development_points(state, BatterSkill.POWER, 1)


def test_atomic_json_round_trip_is_schema_versioned_and_replayable(tmp_path) -> None:
    state = _progressed()
    repository = AtomicJsonCareerRepository(tmp_path)
    path = repository.save("slot_1", state)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["model_version"] == "batter-career-v0.3"
    loaded = repository.load("slot_1")
    assert loaded == state
    assert replay_career(replace(state, games_played=0, experience=0,
        development_points=0, scores=state.origin.starting_scores,
        expired_development_points=0, active_game=None,
        season_purchases=0, season_skill_purchases=(0, 0, 0, 0),
        season_stats=type(state.season_stats)(), career_stats=type(state.career_stats)(),
        completed_seasons=(), events=()), loaded.events) == loaded


def test_unknown_schema_corrupt_file_missing_file_and_bad_id_are_rejected(tmp_path) -> None:
    repository = AtomicJsonCareerRepository(tmp_path)
    with pytest.raises(CareerSaveError, match="not found"):
        repository.load("missing")
    with pytest.raises(ValueError, match="save_id"):
        repository.save("../escape", _progressed())

    path = repository.save("slot", _progressed())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CareerSaveError, match="schema"):
        repository.load("slot")

    path.write_text("not json", encoding="utf-8")
    with pytest.raises(CareerSaveError, match="read"):
        repository.load("slot")


def test_second_save_atomically_replaces_previous_payload(tmp_path) -> None:
    repository = AtomicJsonCareerRepository(tmp_path)
    first = _progressed()
    repository.save("slot", first)
    second = simulate_games(first, 1)
    repository.save("slot", second)
    assert repository.load("slot") == second
    assert list(tmp_path.glob("*.tmp")) == []


def test_partial_plate_appearance_round_trip_is_exact(tmp_path) -> None:
    repository = AtomicJsonCareerRepository(tmp_path)
    origin = create_career(
        player_id="partial-player",
        name="Partial Batter",
        position="OF",
        bats=Handedness.LEFT,
        throws=Handedness.RIGHT,
        archetype=BatterArchetype.BALANCED,
        age=18,
        season_year=2026,
        seed=321,
        season_games=12,
    )
    partial = next_pa(origin)
    repository.save("partial", partial)
    loaded = repository.load("partial")
    assert loaded == partial
    assert loaded.active_game is not None
    assert loaded.experience == 1
    assert replay_career(origin, loaded.events) == loaded


def test_load_rejects_materialized_state_that_disagrees_with_events(tmp_path) -> None:
    repository = AtomicJsonCareerRepository(tmp_path)
    path = repository.save("slot", _progressed())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state"]["experience"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CareerSaveError, match="event log"):
        repository.load("slot")


def test_failed_atomic_replace_keeps_previous_save_and_cleans_temp(
    tmp_path, monkeypatch
) -> None:
    repository = AtomicJsonCareerRepository(tmp_path)
    first = _progressed()
    repository.save("slot", first)

    def fail_replace(_source, _target) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(persistence_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        repository.save("slot", simulate_games(first, 1))
    assert repository.load("slot") == first
    assert list(tmp_path.glob("*.tmp")) == []
