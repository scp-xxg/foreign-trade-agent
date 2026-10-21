"""Deployment guardrails: prevent reusing a teammate's database or services."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trade_team", ROOT / "extensions/foreign_trade/team.py")
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)


class TeamBootstrapTests(unittest.TestCase):
    def test_explicit_home_overrides_foreign_runtime_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "new-home"
            with patch.dict(os.environ, {
                "HUGAGENT_HOME": "/another/instance", "HUGAGENT_CAPS_ROOT": "/another/caps",
                "DATABASE_URL": "sqlite:////another/data.db", "STORAGE_PATH": "/another/storage",
                "FRONTEND_DIST_DIR": "/another/frontend", "SCRIPT_RUNNER_WORKSPACE": "/another/workspace",
            }):
                env = team.runtime_env(home)
            self.assertEqual(env["HUGAGENT_HOME"], str(home))
            self.assertEqual(env["DATABASE_URL"], "sqlite:///" + str(home / "data.db"))
            self.assertEqual(env["HUGAGENT_CAPS_ROOT"], str(home))
            self.assertEqual(env["STORAGE_PATH"], str(home / "storage"))
            self.assertEqual(env["SCRIPT_RUNNER_WORKSPACE"], str(home / "workspace"))
            self.assertEqual(env["HUGAGENT_SKIP_ENV_FILES"], "1")
            self.assertEqual(env["FRONTEND_DIST_DIR"], str(team.FRONTEND / "dist"))
            self.assertFalse(home.exists())

    def test_vite_node_version_boundary(self):
        for version in ("v20.19.0", "22.12.0", "v22.22.1", "24.0.0"):
            self.assertTrue(team.node_supported(version), version)
        for version in ("v18.20.0", "20.18.3", "21.5.0", "22.11.0", "garbage"):
            self.assertFalse(team.node_supported(version), version)

    def test_dry_run_never_creates_data_or_launches_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "do-not-create"
            with patch.object(team.subprocess, "run") as run, patch.object(team.os, "execve") as execute:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    for action in ("setup", "init", "install", "start", "check"):
                        self.assertEqual(team.main([action, "--dry-run", "--app-home", str(home), "--username", "teammate"]), 0)
                run.assert_not_called()
                execute.assert_not_called()
            self.assertFalse(home.exists())

    def test_start_refuses_existing_backend_before_starting_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / "data.db").touch()
            frontend = home / "frontend"
            (frontend / "dist").mkdir(parents=True)
            (frontend / "dist/index.html").write_text("<html></html>")
            with patch.object(team, "FRONTEND", frontend), patch.object(team, "port_open", return_value=True), patch.object(team, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "3001"):
                    team.start(argparse.Namespace(dry_run=False), home, team.runtime_env(home))
                run.assert_not_called()

    def test_start_refuses_uninitialized_home(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(team, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "init"):
                team.start(argparse.Namespace(dry_run=False), Path(temp), team.runtime_env(Path(temp)))
            run.assert_not_called()

    def test_installer_receives_home_prompt_and_account(self):
        with patch.object(team, "run") as run:
            home = Path("/tmp/team-home")
            team.install(home, "alice", team.runtime_env(home), True)
            command = [str(value) for value in run.call_args.args[0]]
            self.assertIn("--apply-homepage-copy", command)
            self.assertIn("--apply-assistant-prompt", command)
            self.assertEqual(command[command.index("--app-home") + 1], str(home))
            self.assertEqual(command[command.index("--username") + 1], "alice")


if __name__ == "__main__":
    unittest.main()