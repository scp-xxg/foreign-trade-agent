#!/usr/bin/env bash
# Linux/WSL/macOS; Docker supplies Python, Node, fonts, frontend and data storage.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install and start Docker Desktop (or Docker Engine + Compose)." >&2
  exit 1
fi
docker compose version >/dev/null
docker info >/dev/null
case "${1:-}" in
  "")
    echo "Open http://127.0.0.1:${SAILAGENT_PORT:-3002} after startup."
    echo "First launch: enter your own username and password in this terminal."
    exec docker compose -f compose.sailagent.yml run --build --rm --service-ports sailagent
    ;;
  --background)
    docker compose -f compose.sailagent.yml run --build --rm -T --no-deps --entrypoint python sailagent -c 'from pathlib import Path; import sys; ready=Path("/data/sailagent-owner.json").is_file(); print("Existing installation found." if ready else "First run ./start.sh interactively to create your own account."); sys.exit(0 if ready else 1)'
    exec docker compose -f compose.sailagent.yml up --build -d --wait --wait-timeout 180
    ;;
  --stop)
    exec docker compose -f compose.sailagent.yml down
    ;;
  --logs)
    exec docker compose -f compose.sailagent.yml logs --tail 100 -f
    ;;
  *)
    echo "Usage: ./start.sh [--background|--stop|--logs]" >&2
    exit 2
    ;;
esac
