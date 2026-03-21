"""Backend configuration. Use env vars to override when deploying."""
from pathlib import Path
import os

import redis as redis_lib

# Storage: "local" (default) or "s3"
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")

# Session artifact directories (mirror S3 layout when STORAGE_MODE is s3)
RAW_DIR = Path(os.getenv("RAW_DIR", "sessions/raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", "sessions/processed"))
PLOTS_DIR = Path(os.getenv("PLOTS_DIR", "sessions/plots"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/ski.db")

# Redis (Railway/Render: set REDIS_URL from your Redis plugin — do not rely on localhost in cloud)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_redis_client: redis_lib.Redis | None = None


def get_redis_client() -> redis_lib.Redis:
    """Lazy Redis client — avoids connect/retry spam at import when REDIS_URL is wrong."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.from_url(
            REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _redis_client

# Upload limit (MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
