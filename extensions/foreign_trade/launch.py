"""Run the self-contained SailAgent image; never ships an account or API key."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

from foreign_trade import team


def saved_owner(home: Path, requested: str | None = None) -> str | None:
    """Select an existing owner without reading credentials or changing accounts."""
    database = home / "data.db"
    accounts = []
    if database.is_file():
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users_shadow'").fetchone():
                accounts = [row[0] for row in db.execute("SELECT username FROM users_shadow WHERE username IS NOT NULL")]
    state = home / "sailagent-owner.json"
    stored = json.loads(state.read_text()).get("username") if state.is_file() else None
    selected = requested or stored
    if selected and ((accounts and selected not in accounts) or (stored and not accounts)):
        raise RuntimeError("Selected owner does not exist; account changes must use the application.")
    if selected:
        return str(selected)
    if len(accounts) == 1:
        return accounts[0]
    if len(accounts) > 1:
        raise RuntimeError("Multiple accounts found; specify --username to select the installation owner.")
    return None


def validate_files() -> None:
    if not (team.FRONTEND / "dist/index.html").is_file():
        raise RuntimeError("Frontend missing. Rebuild the SailAgent image.")
    if not team.PYTHON.is_file():
        raise RuntimeError("Python environment missing. Rebuild the SailAgent image.")


def launch(home: Path, username: str | None, port: int) -> None:
    validate_files()
    home.mkdir(parents=True, exist_ok=True)
    # Keep this FD open across exec; another launcher may not migrate the same DB.
    lock = (home / "sailagent-runtime.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("This data directory is already running; stop its instance first.") from None
    os.set_inheritable(lock.fileno(), True)
    username = saved_owner(home, username)
    if username is None and not sys.stdin.isatty():
        raise RuntimeError("First launch needs an interactive terminal: run ./start.sh and create your own account.")
    env = team.runtime_env(home, port)
    env["HUGAGENT_BIND_HOST"] = "0.0.0.0"
    os.environ.update(env)
    username = team.initialize(home, username, port=port)
    if not (home / "sailagent-owner.json").is_file():
        team.install(home, username, env, False)
    else:
        # Refresh package/roles without overwriting human-edited home copy or prompts.
        team.run([team.PYTHON, team.HERE / "install.py", "--app-home", home,
                  "--username", username, "--port", str(port)], env=env)
    # Public, bundled examples only. A teammate never receives another user's DB.
    team.run([team.PYTHON, "-m", "foreign_trade.import_compliance",
              "--app-home", home, "--username", username], env=env)
    owner_path = home / "sailagent-owner.json"
    temporary = home / "sailagent-owner.json.tmp"
    temporary.write_text(json.dumps({"username": username}, ensure_ascii=False), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(owner_path)
    print("SailAgent initialized. Configure a tool-capable model in Settings → Model services.")
    print("Without a model, workspaces still support deterministic quotes, templates and compliance checks.")
    team.start(SimpleNamespace(port=port, dry_run=False), home, env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-home", type=Path, default=Path("/data"))
    parser.add_argument("--username")
    parser.add_argument("--port", type=team.web_port_number, default=3002)
    args = parser.parse_args(argv)
    try:
        launch(args.app_home.expanduser().resolve(), args.username, args.port)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("SailAgent startup failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
