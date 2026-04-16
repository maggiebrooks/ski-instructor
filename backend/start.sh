#!/bin/sh
set -e

# Start RQ worker in the background (shares filesystem with the API).
python -m backend.rq_render_worker &

# Run uvicorn in the foreground so container signals (SIGTERM) propagate correctly.
exec uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-10000}"
