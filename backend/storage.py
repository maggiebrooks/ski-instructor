"""Storage abstraction layer.

Today: thin wrapper around local filesystem directories.
Later: swap internals for S3 via boto3 -- callers don't change.
"""

from pathlib import Path

from backend.config import RAW_DIR, PROCESSED_DIR, PLOTS_DIR

BUCKETS: dict[str, Path] = {
    "raw": RAW_DIR,
    "processed": PROCESSED_DIR,
    "plots": PLOTS_DIR,
}


def get_path(session_id: str, bucket: str, filename: str | None = None) -> Path:
    """Return the local path for *filename* inside *bucket/session_id*.

    Creates intermediate directories if they don't exist.
    If *filename* is omitted, returns the session directory itself.
    """
    if bucket not in BUCKETS:
        raise ValueError(f"Invalid storage bucket: {bucket}")

    base = BUCKETS[bucket]
    session_dir = base / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    if filename:
        return session_dir / filename

    return session_dir


def write_bytes(session_id: str, bucket: str, filename: str, data: bytes) -> Path:
    """Write *data* to *bucket/session_id/filename* and return the path."""
    path = get_path(session_id, bucket, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


def read_path(session_id: str, bucket: str, filename: str) -> Path:
    """Return the local path for reading (alias of get_path)."""
    return get_path(session_id, bucket, filename)
