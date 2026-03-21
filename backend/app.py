"""ski-ai FastAPI backend."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import PLOTS_DIR, PROCESSED_DIR, RAW_DIR
from backend.routes.upload import router as upload_router
from backend.routes.sessions import router as sessions_router
from backend.routes.metadata import router as metadata_router

# Local disk layout (Docker / Render: ephemeral unless you attach a disk)
for _dir in (RAW_DIR, PROCESSED_DIR, PLOTS_DIR, Path("data"), Path("logs")):
    _dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename="logs/api.log",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

# API sub-app: mounted at /api so it takes precedence over static files
api = FastAPI(title="ski-ai", version="2.0.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
api.include_router(upload_router)
api.include_router(sessions_router)
api.include_router(metadata_router)


@api.get("/health")
def health():
    return {"message": "ski-ai backend running"}


# Main app: mount API first, then static files
app = FastAPI()
app.mount("/api", api)

_FRONTEND_DIR = Path("frontend/dist")
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
