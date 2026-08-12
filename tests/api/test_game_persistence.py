from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from baseball_sim.api.game_repository import GameWriteConflictError, SqliteGameRepository


def test_game_survives_repository_restart_with_exact_replay(tmp_path: Path) -> None:
    database = tmp_path / "games.sqlite3"
    first = SqliteGameRepository(database)
    created = first.create(20260812)
    advanced = first.simulate_half(created.game_id)

    restarted = SqliteGameRepository(database)
    loaded = restarted.get(created.game_id)
    assert loaded == advanced

    resumed = restarted.next_pa(created.game_id)
    assert len(resumed.events) == len(advanced.events) + 1
    assert SqliteGameRepository(database).get(created.game_id) == resumed


def test_reset_seed_and_empty_event_stream_survive_restart(tmp_path: Path) -> None:
    database = tmp_path / "games.sqlite3"
    repository = SqliteGameRepository(database)
    created = repository.create(1)
    repository.next_pa(created.game_id)
    reset = repository.reset(created.game_id, 99)

    loaded = SqliteGameRepository(database).get(created.game_id)
    assert loaded == reset
    assert loaded.initial_state.seed == 1
    assert loaded.state.seed == 99
    assert loaded.events == []


def test_corrupt_game_isolated_while_healthy_game_loads(tmp_path: Path) -> None:
    database = tmp_path / "games.sqlite3"
    repository = SqliteGameRepository(database)
    healthy = repository.create(7)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO games(game_id, persistence_version, payload_json) VALUES (?, ?, ?)",
            ("corrupt", "game-sqlite-v1", "{not-json"),
        )

    restarted = SqliteGameRepository(database)
    assert restarted.get(healthy.game_id) == healthy


def test_stale_writer_cannot_regress_persisted_game(tmp_path: Path) -> None:
    database = tmp_path / "games.sqlite3"
    first = SqliteGameRepository(database)
    created = first.create(17)
    stale = SqliteGameRepository(database)
    expected = first.next_pa(created.game_id)
    with pytest.raises(GameWriteConflictError):
        stale.next_pa(created.game_id)
    assert SqliteGameRepository(database).get(created.game_id) == expected


def test_failed_save_does_not_publish_candidate_to_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SqliteGameRepository(tmp_path / "games.sqlite3")
    created = repository.create(23)

    def fail(*_args: object) -> None:
        raise sqlite3.OperationalError("injected write failure")

    monkeypatch.setattr(repository, "_save_candidate", fail)
    with pytest.raises(sqlite3.OperationalError):
        repository.next_pa(created.game_id)
    assert repository.get(created.game_id) == created
