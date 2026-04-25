#!/usr/bin/env bash
# One command: API + RQ worker + Vite + Redis when needed.
# Run from anywhere:  bash scripts/dev.sh
# Or:  chmod +x scripts/dev.sh && ./scripts/dev.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HONCHO="${ROOT}/venv/bin/honcho"
if [[ ! -x "$HONCHO" ]]; then
  echo "Missing ${HONCHO}. Activate venv or run: python3 -m pip install honcho" >&2
  exit 1
fi

redis_listening() {
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null | grep -q PONG
    return $?
  fi
  # No redis-cli: try bash TCP probe (bash 3.2+ on macOS)
  (echo >/dev/tcp/127.0.0.1/6379) 2>/dev/null
}

if redis_listening; then
  echo "Redis already on 127.0.0.1:6379 — starting api, worker, web only."
  exec "$HONCHO" start
else
  echo "Starting Redis + api + worker + web (Procfile.with-redis)."
  exec "$HONCHO" -f Procfile.with-redis start
fi
