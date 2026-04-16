#!/bin/sh
set -e

echo "Starting worker..."
# Use RQ CLI (same queue as upload enqueues). --url matches backend.config / Railway.
rq worker ski-pipeline --url "${REDIS_URL:-redis://localhost:6379}" &

echo "Starting API..."
uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8080}"
