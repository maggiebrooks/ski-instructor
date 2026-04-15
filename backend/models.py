"""Jobs table: tracks upload -> pipeline lifecycle for each session."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DB_PATH = str(Path("data/ski.db").resolve())


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id          TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL,
            session_hash    TEXT,
            status          TEXT NOT NULL DEFAULT 'processing',
            progress_stage  TEXT NOT NULL DEFAULT 'processing',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            error_message   TEXT
        )
    """)
    # Migrate older databases that lack session_hash
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN session_hash TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()


def create_job(
    session_id: str,
    *,
    session_hash: str | None = None,
    db_path: str | None = None,
) -> str:
    """Insert a new job row and return its job_id."""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    job_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO jobs (job_id, session_id, session_hash, status,
                             progress_stage, created_at, updated_at)
           VALUES (?, ?, ?, 'processing', 'queued', ?, ?)""",
        (job_id, session_id, session_hash, now, now),
    )
    conn.commit()
    conn.close()
    return job_id


def get_job(session_id: str, *, db_path: str | None = None) -> dict | None:
    """Look up the most recent job for *session_id*."""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    row = conn.execute(
        """SELECT job_id, session_id, session_hash, status, progress_stage,
                  created_at, updated_at, error_message
           FROM jobs WHERE session_id = ?
           ORDER BY created_at DESC LIMIT 1""",
        (session_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def lookup_by_hash(
    session_hash: str, *, db_path: str | None = None
) -> str | None:
    """Return the session_id of a completed job with this hash, or None."""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    row = conn.execute(
        """SELECT session_id FROM jobs
           WHERE session_hash = ? AND status IN ('processing', 'complete')
           ORDER BY created_at DESC LIMIT 1""",
        (session_hash,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row["session_id"]


def update_job(
    session_id: str,
    stage: str,
    *,
    error: str | None = None,
    db_path: str | None = None,
) -> None:
    """Update progress_stage (and status) for the latest job of *session_id*."""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    now = datetime.now(timezone.utc).isoformat()
    status = "error" if stage == "error" else ("complete" if stage == "complete" else "processing")
    conn.execute(
        """UPDATE jobs
           SET status = ?, progress_stage = ?, updated_at = ?, error_message = ?
           WHERE job_id = (
               SELECT job_id FROM jobs
               WHERE session_id = ?
               ORDER BY created_at DESC LIMIT 1
           )""",
        (status, stage, now, error, session_id),
    )
    conn.commit()
    conn.close()


def delete_session_records(session_id: str, *, db_path: str | None = None) -> None:
    """Remove analytics rows for *session_id* from the ski SQLite DB.

    Deletes in order: ``turns`` (via runs), ``runs``, ``sessions``, and all
    ``jobs`` rows for this session.
    """
    from data.database import init_db

    path = db_path or DB_PATH
    conn = init_db(path)
    _ensure_table(conn)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """DELETE FROM turns WHERE run_id IN
           (SELECT run_id FROM runs WHERE session_id = ?)""",
        (session_id,),
    )
    conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
