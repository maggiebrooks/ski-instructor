"""Backend configuration. Use env vars to override when deploying."""
from pathlib import Path
import os

import redis

# Storage: "local" (default) or "s3"
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")

# Session artifact directories (mirror S3 layout when STORAGE_MODE is s3)
RAW_DIR = Path(os.getenv("RAW_DIR", "sessions/raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", "sessions/processed"))
PLOTS_DIR = Path(os.getenv("PLOTS_DIR", "sessions/plots"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/ski.db")

# Redis — on Railway set REDIS_URL from your Redis service (never rely on bare localhost in prod)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
