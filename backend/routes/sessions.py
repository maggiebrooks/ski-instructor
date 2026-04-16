"""Session retrieval endpoints: status, report, list, plot serving, delete."""

import datetime
import json
import logging
import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.config import PERSISTENT_DIR, PLOTS_DIR, PROCESSED_DIR, RAW_DIR
from backend.models import DB_PATH, delete_session_records, get_job

logger = logging.getLogger(__name__)

router = APIRouter()


def _session_id_invalid(session_id: str) -> bool:
    return ".." in session_id or "/" in session_id or "\\" in session_id


def _session_exists(session_id: str) -> bool:
    """True if this session has artifacts, DB rows, or a job record."""
    if (PROCESSED_DIR / session_id / "report.json").exists():
        return True
    if (RAW_DIR / session_id).is_dir():
        return True
    if (PLOTS_DIR / session_id).is_dir():
        return True
    if get_job(session_id) is not None:
        return True
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None
    finally:
        conn.close()


@router.delete("/session/{session_id}")
def delete_session(session_id: str):
    """Remove session artifacts, plots, raw upload, and DB rows."""
    if _session_id_invalid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session id")

    if not _session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    for base in (RAW_DIR, PROCESSED_DIR, PLOTS_DIR):
        path = base / session_id
        if path.exists():
            shutil.rmtree(path)

    delete_session_records(session_id)
    return {"status": "deleted"}


@router.get("/session/{session_id}")
def get_session(session_id: str):
    """Return processing status and report (if complete) for a session."""
    job = get_job(session_id)
    report_path = PROCESSED_DIR / session_id / "report.json"

    if not job and not report_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    report = None
    if report_path.exists():
        with open(report_path) as f:
            report = json.load(f)

    if job:
        out = {
            "session_id": session_id,
            "status": job["status"],
            "progress": job["progress_stage"],
            "report": report,
        }
        if job.get("error_message"):
            out["error"] = job["error_message"]
        return out
    # Legacy: no job row (processed before jobs table), but report exists
    return {
        "session_id": session_id,
        "status": "complete",
        "progress": "complete",
        "report": report,
    }


@router.get("/sessions")
def list_sessions():
    """Return a summary list of all completed sessions."""
    sessions = []
    if not PROCESSED_DIR.exists():
        logger.warning("list_sessions: PROCESSED_DIR does not exist: %s", PROCESSED_DIR)
        return sessions

    entries = list(PROCESSED_DIR.iterdir())
    logger.info(
        "list_sessions: PROCESSED_DIR=%s, entries=%d, names=%s",
        PROCESSED_DIR,
        len(entries),
        [e.name for e in entries[:20]],
    )

    for session_dir in sorted(entries):
        if not session_dir.is_dir():
            continue
        report_path = session_dir / "report.json"
        if not report_path.exists():
            continue
        with open(report_path) as f:
            report = json.load(f)
        mtime = report_path.stat().st_mtime
        created_at = datetime.datetime.fromtimestamp(
            mtime, tz=datetime.timezone.utc
        ).isoformat()
        sessions.append({
            "session_id": session_dir.name,
            "status": "complete",
            "summary": report.get("summary"),
            "scores": report.get("scores"),
            "top_insight": report.get("top_insight"),
            "created_at": created_at,
        })

    sessions.sort(key=lambda s: s["created_at"], reverse=True)
    return sessions


@router.get("/debug/paths")
def debug_paths():
    """Temporary debug: show resolved storage paths and what's on disk."""
    import os
    result = {
        "PERSISTENT_DIR": str(PERSISTENT_DIR),
        "PERSISTENT_DIR_exists": PERSISTENT_DIR.exists(),
        "PROCESSED_DIR": str(PROCESSED_DIR),
        "PROCESSED_DIR_exists": PROCESSED_DIR.exists(),
        "RAW_DIR": str(RAW_DIR),
        "RAW_DIR_exists": RAW_DIR.exists(),
        "PLOTS_DIR": str(PLOTS_DIR),
        "cwd": os.getcwd(),
    }
    if PROCESSED_DIR.exists():
        result["processed_entries"] = [
            {
                "name": e.name,
                "is_dir": e.is_dir(),
                "has_report": (e / "report.json").exists() if e.is_dir() else False,
            }
            for e in sorted(PROCESSED_DIR.iterdir())
        ]
    if RAW_DIR.exists():
        result["raw_entries"] = [e.name for e in sorted(RAW_DIR.iterdir())[:20]]
    return result


@router.get("/session/{session_id}/plot/{plot_name}")
def get_plot(session_id: str, plot_name: str):
    """Serve a plot image for a session."""
    if ".." in plot_name or "/" in plot_name or "\\" in plot_name:
        raise HTTPException(status_code=400, detail="Invalid plot name")

    plot_path = PLOTS_DIR / session_id / plot_name
    if not plot_path.exists():
        raise HTTPException(status_code=404, detail="Plot not found")

    return FileResponse(plot_path)
