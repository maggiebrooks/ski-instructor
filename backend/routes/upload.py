"""Upload endpoint: accept a Sensor Logger ZIP and enqueue pipeline job."""

import hashlib
import shutil
import zipfile
import io
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, UploadFile, HTTPException
from rq import Queue

from backend.config import RAW_DIR, MAX_UPLOAD_MB, redis_client
from backend.models import create_job, lookup_by_hash

logger = logging.getLogger(__name__)

router = APIRouter()

SKIP_PREFIXES = ("__MACOSX", ".")


def _get_queue() -> Queue:
    return Queue("ski-pipeline", connection=redis_client)


def _flatten_single_top_level(session_dir: Path) -> None:
    """If session_dir contains a single real folder, move its contents up."""
    entries = [
        p
        for p in session_dir.iterdir()
        if p.name and not p.name.startswith(SKIP_PREFIXES)
    ]
    if len(entries) != 1 or not entries[0].is_dir():
        return
    inner = entries[0]
    for child in inner.iterdir():
        if child.name.startswith(SKIP_PREFIXES):
            continue
        shutil.move(str(child), str(session_dir / child.name))
    inner.rmdir()


@router.post("/upload-session")
async def upload_session(file: UploadFile):
    contents = await file.read()

    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB limit")

    if not zipfile.is_zipfile(io.BytesIO(contents)):
        raise HTTPException(400, "File is not a valid ZIP archive")

    with zipfile.ZipFile(io.BytesIO(contents)) as zf:
        names = zf.namelist()
        has_accel = any("Accelerometer.csv" in n for n in names)
        has_gyro = any("Gyroscope.csv" in n for n in names)
        if not has_accel or not has_gyro:
            raise HTTPException(
                400,
                "ZIP must contain Accelerometer.csv and Gyroscope.csv",
            )

    session_hash = hashlib.sha256(contents).hexdigest()

    existing = lookup_by_hash(session_hash)
    if existing:
        logger.info("Duplicate upload detected (hash=%s) -> %s", session_hash[:12], existing)
        return {"session_id": existing, "status": "complete", "duplicate": True}

    session_id = uuid4().hex
    session_dir = RAW_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(contents)) as zf:
        zf.extractall(session_dir)
        _flatten_single_top_level(session_dir)

    logger.info("Uploaded session %s (%d bytes, hash=%s)", session_id, len(contents), session_hash[:12])

    create_job(session_id, session_hash=session_hash)

    queue = _get_queue()
    queue.enqueue("backend.worker.run_pipeline", session_id)

    return {"session_id": session_id, "status": "processing"}
