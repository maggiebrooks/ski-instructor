"""Backend configuration. Use env vars to override when deploying."""
from pathlib import Path
import os

import redis

# Anchor all relative defaults to the repo / container root (/app in Docker).
BASE_DIR = Path(__file__).resolve().parent.parent

# Persistent storage root.  On Railway: create a Volume, mount it (e.g. at
# /persist), then set  PERSISTENT_DIR=/persist  on the service.  Locally this
# just falls back to the repo root so nothing changes.
PERSISTENT_DIR = Path(os.getenv("PERSISTENT_DIR", str(BASE_DIR)))

# Storage: "local" (default) or "s3"
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")

# Session artifact directories — live on the persistent volume so they survive
# deploys.
RAW_DIR = Path(os.getenv("RAW_DIR", str(PERSISTENT_DIR / "sessions" / "raw")))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", str(PERSISTENT_DIR / "sessions" / "processed")))
PLOTS_DIR = Path(os.getenv("PLOTS_DIR", str(PERSISTENT_DIR / "sessions" / "plots")))

# Data + logs also on persistent storage.
DATA_DIR = PERSISTENT_DIR / "data"
LOGS_DIR = PERSISTENT_DIR / "logs"

for _d in (RAW_DIR, PROCESSED_DIR, PLOTS_DIR, DATA_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Database — SQLite on the persistent volume.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'ski.db'}")

# Redis — on Railway set REDIS_URL from your Redis service (never rely on bare localhost in prod)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
