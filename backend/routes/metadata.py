"""Metadata endpoint: serve skier/ski/session metadata for a session."""

import logging
from pathlib import Path

from fastapi import APIRouter

from backend.config import RAW_DIR
from ski.metadata.metadata_loader import MetadataLoader

logger = logging.getLogger(__name__)

router = APIRouter()

DATA_DIR = Path("data").resolve()


@router.get("/session/{session_id}/metadata")
def get_metadata(session_id: str):
    """Return metadata for a session, including resolved skier/ski profiles."""
    loader = MetadataLoader()

    # Try uploaded sessions first, then legacy data/ sessions
    session_meta = loader.load_session_metadata(RAW_DIR / session_id)
    if session_meta is None and DATA_DIR.is_dir():
        for d in DATA_DIR.iterdir():
            if d.is_dir() and session_id in d.name:
                session_meta = loader.load_session_metadata(d)
                if session_meta:
                    break

    if not session_meta:
        return {}

    result = {"session": session_meta}

    skier_id = session_meta.get("skier")
    if skier_id:
        skier = loader.load_skier_profile(skier_id)
        if skier:
            result["skier"] = skier

    ski_id = session_meta.get("ski")
    if ski_id:
        ski = loader.load_ski_profile(ski_id)
        if ski:
            result["ski"] = ski

    return result
