"""Verify team installs can skip unrelated repository configuration files."""
import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class EnvIsolationTests(unittest.TestCase):
    def test_opt_out_never_opens_repository_env(self):
        source = (ROOT / "src/backend/core/config/environment.py").read_text()
        fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_load_env_files")
        code = compile(ast.Module(body=[fn], type_ignores=[]), str(ROOT), "exec")
        def reject_read(*args, **kwargs):
            raise AssertionError("Repository .env must not be read")
        namespace = {"os": os, "dotenv_values": reject_read}
        exec(code, namespace)
        for value in ("1", "true", "YES"):
            with self.subTest(value=value), patch.dict(os.environ, {"HUGAGENT_SKIP_ENV_FILES": value}):
                namespace["_load_env_files"]()

if __name__ == "__main__":
    unittest.main()
