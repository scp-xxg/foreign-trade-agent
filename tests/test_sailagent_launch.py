"""Deployment failure modes and persisted owner selection; no live services."""
from pathlib import Path
import json
import sqlite3
import subprocess
from unittest.mock import patch

import pytest
from foreign_trade import launch


@pytest.fixture(autouse=True)
def isolated_launch_environment(monkeypatch):
    # launch writes runtime_env in-process before exec; never leak its temporary
    # app-home/profile into tests using their own database and host registry.
    monkeypatch.setattr(launch.os, "environ", dict(launch.os.environ))


def users(home, names):
    with sqlite3.connect(home / "data.db") as db:
        db.execute("CREATE TABLE users_shadow(username TEXT)")
        db.executemany("INSERT INTO users_shadow VALUES (?)", [(x,) for x in names])


def test_restarts_reuse_selected_owner_without_touching_accounts(tmp_path):
    users(tmp_path, ["alice", "teammate"])
    (tmp_path / "sailagent-owner.json").write_text(json.dumps({"username": "alice"}))
    assert launch.saved_owner(tmp_path) == "alice"
    assert launch.saved_owner(tmp_path, "teammate") == "teammate"
    with sqlite3.connect(tmp_path / "data.db") as db:
        assert db.execute("SELECT username FROM users_shadow ORDER BY username").fetchall() == [("alice",), ("teammate",)]


def test_single_existing_user_is_recovered_but_ambiguous_or_missing_owner_fails(tmp_path):
    users(tmp_path, ["alice"])
    assert launch.saved_owner(tmp_path) == "alice"
    with pytest.raises(RuntimeError, match="does not exist"):
        launch.saved_owner(tmp_path, "not-a-user")
    with sqlite3.connect(tmp_path / "data.db") as db:
        db.execute("INSERT INTO users_shadow VALUES ('bob')")
    with pytest.raises(RuntimeError, match="Multiple accounts"):
        launch.saved_owner(tmp_path)


def test_fresh_noninteractive_start_fails_before_account_or_database_write(tmp_path):
    with patch.object(launch, "validate_files"), patch.object(launch.sys.stdin, "isatty", return_value=False), patch.object(launch.team, "initialize") as initialize:
        with pytest.raises(RuntimeError, match="interactive terminal"):
            launch.launch(tmp_path, None, 3002)
    initialize.assert_not_called()
    assert not (tmp_path / "data.db").exists()
    assert not (tmp_path / "sailagent-owner.json").exists()


def test_existing_instance_lock_refuses_migration(tmp_path):
    import fcntl
    with (tmp_path / "sailagent-runtime.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.object(launch, "validate_files"), patch.object(launch.team, "initialize") as initialize:
            with pytest.raises(RuntimeError, match="already running"):
                launch.launch(tmp_path, None, 3002)
    initialize.assert_not_called()


def test_setup_failure_stops_before_start_and_keeps_failed_install_visible(tmp_path):
    users(tmp_path, ["alice"])
    with patch.object(launch, "validate_files"), patch.object(launch.team, "initialize", return_value="alice"), patch.object(launch.team, "install", side_effect=RuntimeError("install failed")), patch.object(launch.team, "start") as start:
        with pytest.raises(RuntimeError, match="install failed"):
            launch.launch(tmp_path, None, 3002)
    start.assert_not_called()
    assert not (tmp_path / "sailagent-owner.json").exists()


def test_restart_updates_package_without_reapplying_home_or_system_prompt(tmp_path):
    users(tmp_path, ["alice"])
    (tmp_path / "sailagent-owner.json").write_text(json.dumps({"username": "alice"}))
    with patch.object(launch, "validate_files"), patch.object(launch.team, "initialize", return_value="alice"), patch.object(launch.team, "install") as install, patch.object(launch.team, "run") as run, patch.object(launch.team, "start") as start:
        launch.launch(tmp_path, None, 3002)
    install.assert_not_called()
    assert len(run.call_args_list) == 2
    command = [str(x) for x in run.call_args_list[0].args[0]]
    assert "install.py" in command[1]
    assert "--apply-homepage-copy" not in command and "--apply-assistant-prompt" not in command
    start.assert_called_once()


def test_owner_marker_without_database_refuses_silent_reinitialization(tmp_path):
    (tmp_path / "sailagent-owner.json").write_text(json.dumps({"username": "alice"}))
    with pytest.raises(RuntimeError, match="does not exist"):
        launch.saved_owner(tmp_path)
    assert not (tmp_path / "data.db").exists()
