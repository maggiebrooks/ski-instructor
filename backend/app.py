"""ski-ai FastAPI backend."""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import BASE_DIR, PLOTS_DIR, PROCESSED_DIR, RAW_DIR
from backend.routes import metadata, sessions, upload


def _init_deployment_logging() -> None:
    """Railway: log to stdout, throttle noisy loggers (avoids 500 logs/sec limit)."""
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_SERVICE_NAME")
    )
    if railway:
        logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn").setLevel(logging.INFO)
        logging.getLogger("redis").setLevel(logging.WARNING)
        logging.getLogger("rq").setLevel(logging.INFO)
    else:
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=level,
            format=fmt,
            filename=str(log_dir / "api.log"),
            force=True,
        )


_init_deployment_logging()

# config.py already creates RAW_DIR, PROCESSED_DIR, PLOTS_DIR, data/, logs/ on import.


@asynccontextmanager
async def _api_lifespan(_: FastAPI):
    """Re-apply uvicorn logger levels after workers attach (Railway)."""
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    yield


# --- API app (all REST routes live here; mounted at /api on the outer `app`) ---
# Swagger UI: GET /api/docs   |   OpenAPI JSON: GET /api/openapi.json
# The root `app` has no route handlers except mounts — do not use /docs on the root for API.
api = FastAPI(title="ski-ai", version="2.0.0", lifespan=_api_lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
api.include_router(upload.router)
api.include_router(sessions.router)
api.include_router(metadata.router)


@api.get("/health")
def health():
    return {"message": "ski-ai backend running"}


# Main app: mount API first, then static files
app = FastAPI()
app.mount("/api", api)

_FRONTEND_DIR = Path("frontend/dist")
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
