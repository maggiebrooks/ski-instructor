"""Backend configuration. Use env vars to override when deploying."""
from pathlib import Path
import os

import redis

# Anchor all relative defaults to the repo / container root (/app in Docker).
BASE_DIR = Path(__file__).resolve().parent.parent

# Storage: "local" (default) or "s3"
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")

# Session artifact directories (absolute so API + worker always agree).
RAW_DIR = Path(os.getenv("RAW_DIR", str(BASE_DIR / "sessions" / "raw")))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", str(BASE_DIR / "sessions" / "processed")))
PLOTS_DIR = Path(os.getenv("PLOTS_DIR", str(BASE_DIR / "sessions" / "plots")))

for _d in (RAW_DIR, PROCESSED_DIR, PLOTS_DIR, BASE_DIR / "data", BASE_DIR / "logs"):
    _d.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'ski.db'}")

# Redis — on Railway set REDIS_URL from your Redis service (never rely on bare localhost in prod)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
