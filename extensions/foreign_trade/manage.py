"""Manage only this project's loopback demo MCP and build its importable plugin."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / ".runtime"
PID_FILE = RUNTIME / "server.pid"
SERVER = HERE / "mcp_server.py"
URL = "http://127.0.0.1:9120"


def health() -> dict | None:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/health", timeout=2) as response:
            result = json.load(response)
        if result.get("service") == "foreign-trade-demo" and result.get("ok"):
            return result
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return None


def start() -> dict:
    current = health()
    if current:
        return {"status": "already_running", "url": URL + "/mcp", **current}
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 9120)) == 0:
            raise RuntimeError("Port 9120 is occupied by an unrecognized service.")
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / "server.log").open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=HERE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid), encoding="ascii")
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError("Demo MCP exited; inspect .runtime/server.log.")
        current = health()
        if current:
            return {"status": "started", "pid": proc.pid, "url": URL + "/mcp", **current}
        time.sleep(0.25)
    raise RuntimeError("Demo MCP did not become ready; inspect .runtime/server.log.")


def stop() -> dict:
    if not PID_FILE.exists():
        return {"status": "no_managed_process"}
    pid = int(PID_FILE.read_text().strip())
    proc = Path("/proc") / str(pid)
    if not proc.exists():
        return {"status": "already_stopped"}
    argv = (proc / "cmdline").read_bytes().split(b"\0")
    if str(SERVER).encode() not in argv or (proc / "cwd").resolve() != HERE:
        raise RuntimeError("PID no longer belongs to this project's demo MCP.")
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not proc.exists() or health() is None:
            return {"status": "stopped", "pid": pid}
        time.sleep(0.25)
    raise RuntimeError("Demo MCP is still stopping.")


def build() -> dict:
    plugin = HERE / "plugin"
    required = [
        plugin / "plugin.json", plugin / "mcp.json",
        plugin / "skills/inquiry-quote/SKILL.md",
        plugin / "skills/buyer-inquiry-followup/SKILL.md",
        plugin / "skills/product-content/SKILL.md",
        plugin / "skills/cross-role-collaboration/SKILL.md",
        plugin / "HOST_REQUIREMENTS.md",
        HERE.parents[1] / "docs/CHAT_PLUGIN.md",
        HERE.parents[1] / "docs/CHAT_PLUGIN_ACCEPTANCE.md",
        HERE.parents[1] / "docs/SCENARIO_THREE.md",
        HERE.parents[1] / "docs/ACCEPTANCE_20261028.md",
        HERE / "engine.py", HERE / "catalog.json", SERVER,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing package files: " + ", ".join(missing))
    out = HERE / "dist/foreign-trade-demo.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(plugin.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(plugin).as_posix())
        for name in ("engine.py", "catalog.json", "mcp_server.py"):
            archive.write(HERE / name, "runtime/" + name)
        if (HERE / "README.md").is_file():
            archive.write(HERE / "README.md", "README.md")
        archive.write(HERE.parents[1] / "docs/CHAT_PLUGIN.md", "CHAT_PLUGIN.md")
        archive.write(HERE.parents[1] / "docs/CHAT_PLUGIN_ACCEPTANCE.md", "CHAT_PLUGIN_ACCEPTANCE.md")
        archive.write(HERE.parents[1] / "docs/SCENARIO_THREE.md", "SCENARIO_THREE.md")
        archive.write(HERE.parents[1] / "docs/ACCEPTANCE_20261028.md", "ACCEPTANCE_20261028.md")
        for path in sorted((HERE / "demo_product").iterdir()):
            if path.is_file() and path.suffix in {".csv", ".txt", ".json", ".png", ".jpg"}:
                archive.write(path, "demo_product/" + path.name)
    return {"status": "built", "path": str(out), "bytes": out.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "build"))
    args = parser.parse_args()
    try:
        result = {
            "start": start, "stop": stop, "build": build,
            "status": lambda: {"running": health() is not None, "url": URL + "/mcp"},
        }[args.action]()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
