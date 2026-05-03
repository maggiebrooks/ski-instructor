"""Cleanup script for raw session lifecycle.

Deletes raw session folders older than RAW_RETENTION_DAYS.

Optionally requires a processed report to exist before deleting raw (safer).

Usage:
  python scripts/cleanup_raw_sessions.py
  RAW_RETENTION_DAYS=14 python scripts/cleanup_raw_sessions.py
"""

from __future__ import annotations

import time
from pathlib import Path

from backend.config import (
    PROCESSED_DIR,
    RAW_DELETE_REQUIRES_PROCESSED,
    RAW_DIR,
    RAW_RETENTION_DAYS,
)


def _is_old(path: Path, *, cutoff_ts: float) -> bool:
    try:
        # Use directory mtime as a proxy; raw uploads are written once.
        return path.stat().st_mtime < cutoff_ts
    except OSError:
        return False


def main() -> int:
    cutoff_ts = time.time() - (RAW_RETENTION_DAYS * 24 * 60 * 60)
    deleted = 0
    skipped = 0

    if not RAW_DIR.exists():
        print(f"RAW_DIR does not exist: {RAW_DIR}")
        return 0

    for session_dir in sorted(RAW_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        if not _is_old(session_dir, cutoff_ts=cutoff_ts):
            continue

        session_id = session_dir.name
        if RAW_DELETE_REQUIRES_PROCESSED:
            report = PROCESSED_DIR / session_id / "report.json"
            if not report.exists():
                skipped += 1
                continue

        for p in sorted(session_dir.rglob("*"), reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except OSError:
                # Best-effort: keep going; next run can retry.
                skipped += 1
                break
        else:
            try:
                session_dir.rmdir()
                deleted += 1
            except OSError:
                skipped += 1

    print(
        f"cleanup_raw_sessions: retention_days={RAW_RETENTION_DAYS}, "
        f"requires_processed={RAW_DELETE_REQUIRES_PROCESSED}, "
        f"deleted={deleted}, skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

