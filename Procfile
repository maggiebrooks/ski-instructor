# Local development: run from repo root with `honcho start` (see README).
# Expects Redis already on localhost:6379 (e.g. brew services, Docker, or redis-server).
# If nothing is using 6379 yet: `honcho -f Procfile.with-redis start`
api: uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
worker: rq worker ski-pipeline --url "${REDIS_URL:-redis://localhost:6379}"
web: npm run dev --prefix frontend
