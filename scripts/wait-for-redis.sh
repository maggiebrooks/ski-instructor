#!/usr/bin/env bash
# Wait until Redis accepts connections on 127.0.0.1:6379.
# Used by Procfile.with-redis so the RQ worker does not start before redis-server is ready.

set -euo pipefail

if command -v redis-cli >/dev/null 2>&1; then
  for _ in $(seq 1 100); do
    if redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null | grep -q PONG; then
      exit 0
    fi
    sleep 0.05
  done
  echo "wait-for-redis: Redis did not respond on 127.0.0.1:6379 within ~5s" >&2
  exit 1
fi

echo "wait-for-redis: redis-cli not in PATH; sleeping 0.5s (install redis for a reliable wait)" >&2
sleep 0.5
exit 0
