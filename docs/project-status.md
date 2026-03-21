# ski-ai Project Status

*Last updated: March 2026*

## What This Is

A ski analytics platform that turns iPhone sensor data into biomechanical
feedback. You ski with your phone in your pocket, export the sensor logs,
upload them, and get a detailed breakdown of your technique scored against
the PSIA Five Fundamentals of Alpine Skiing.

## Architecture Overview

```
Phone (Sensor Logger app)
    │
    ▼ .zip export
┌───────────────────────────────────────────────┐
│  Frontend (React + Vite)                       │
│  Upload.tsx → Session.tsx (polling) → Results   │
└───────────────┬───────────────────────────────┘
                │ POST /api/upload-session
                ▼
┌───────────────────────────────────────────────┐
│  Backend (FastAPI :8000)                       │
│  ├─ routes/upload.py    validate + hash + enqueue│
│  ├─ routes/sessions.py  status, report, plots   │
│  ├─ routes/metadata.py  skier/ski profiles       │
│  ├─ models.py           jobs table (SQLite)      │
│  └─ storage.py          local FS (S3-ready)      │
└───────────────┬───────────────────────────────┘
                │ Redis Queue
                ▼
┌───────────────────────────────────────────────┐
│  Worker (RQ)                                   │
│  backend/worker.py → SessionProcessor          │
│  ├─ Ingestion (8 sensor CSVs → unified DF)     │
│  ├─ Preprocessing (Butterworth filter, 20 Hz)  │
│  ├─ Segmentation (skiing / lift / idle)         │
│  ├─ Turn Detection (gyro_z peak finding)        │
│  ├─ Feature Modules (pelvis + carving phase)    │
│  ├─ Analytics (TurnAnalyzer + TurnInsights)     │
│  └─ Output (report.json, turn_signature.png)    │
└───────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────┐
│  Storage                                       │
│  sessions/raw/          uploaded ZIPs           │
│  sessions/processed/    report.json, CSVs       │
│  sessions/plots/        turn_signature.png      │
│  data/ski.db            SQLite (sessions/runs/turns/jobs)│
└───────────────────────────────────────────────┘
```

## What's Built

### Analytics Pipeline (complete)

| Component | File | What It Does |
|-----------|------|-------------|
| Ingestion | `transformations/process_session.py` | Merges 8 Sensor Logger CSVs into one time-aligned DataFrame |
| Preprocessing | same file | Butterworth LP filter (5 Hz), downsample 100 Hz -> 20 Hz |
| Segmentation | same file | Altitude-rate classification: skiing / lift / idle |
| Turn Detection | same file | Peak detection on gyro_z per run |
| Feature Modules | `features/modules/` | Pluggable per-turn metrics (PelvisTurnModule, CarvingPhaseModule) |
| Orchestration | `ski/processing/session_processor.py` | `SessionProcessor.process()` runs the full pipeline |
| Analytics | `ski/analysis/turn_analyzer.py` | Read-only DB queries, session metrics, cross-session comparison |
| Insights | `ski/analysis/turn_insights.py` | 6 movement scores, physics-based normalization, Five Fundamentals feedback |
| Visualization | `ski/analysis/turn_signature.py` | Median turn signature curves with percentile shading |
| Metadata | `ski/metadata/metadata_loader.py` | YAML-based skier/ski/session profiles |

### Backend API (complete)

| Endpoint | Description |
|----------|-------------|
| `POST /api/upload-session` | Upload ZIP, validate, hash for dedup, enqueue worker |
| `GET /api/session/{id}` | Processing status + report (polls during processing) |
| `GET /api/sessions` | List all completed sessions |
| `GET /api/session/{id}/plot/{name}` | Serve plot PNGs |
| `GET /api/session/{id}/metadata` | Skier/ski/session metadata |
| `GET /api/health` | Health check |

**Key backend features:**
- SHA-256 duplicate upload detection
- Multi-stage progress tracking (processing -> analyzing -> generating_plots -> complete)
- Error capture with full tracebacks in worker logs
- Storage abstraction layer (local FS today, S3 later)
- File logging (`logs/api.log`, `logs/worker.log`)
- Job tracking via SQLite `jobs` table

### Frontend (skeleton complete)

| File | Purpose |
|------|---------|
| `frontend/src/pages/Upload.tsx` | ZIP file input, upload with error handling |
| `frontend/src/pages/Session.tsx` | Polls for status, shows progress, renders results + plot |
| `frontend/src/components/Progress.tsx` | Pipeline stage indicator |
| `frontend/src/api.ts` | Axios wrapper for backend calls |

Vite dev server proxies `/api` to FastAPI. Production build served via
`StaticFiles` mount at `/` in the backend.

### Test Suite (160 tests)

| File | Tests | Covers |
|------|------:|--------|
| `test_backend.py` | 34 | Upload, sessions, plots, jobs, storage, dedup, metadata |
| `test_turn_insights.py` | 50 | Movement scores, normalization, fundamentals |
| `test_pipeline.py` | 41 | Ingestion, preprocessing, segmentation, turns, features |
| `test_turn_analyzer.py` | 25 | DB queries, metrics, comparison |
| `test_metadata_loader.py` | 10 | YAML loading, profile resolution |

## Project Structure

```
ski-ai/
├── backend/
│   ├── app.py              FastAPI app, CORS, static mount, route registration
│   ├── config.py           Env-based configuration
│   ├── models.py           Jobs table (create/get/update/lookup_by_hash)
│   ├── storage.py          Storage abstraction (local -> S3 later)
│   ├── worker.py           RQ worker: runs pipeline, writes artifacts
│   └── routes/
│       ├── upload.py       POST /api/upload-session
│       ├── sessions.py     GET session status, list, plots
│       └── metadata.py     GET session metadata
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx         React Router (/, /session/:id)
│   │   ├── api.ts          Axios helpers
│   │   ├── pages/          Upload.tsx, Session.tsx
│   │   └── components/     Progress.tsx
│   ├── vite.config.ts      Dev proxy /api -> :8000
│   └── dist/               Production build (served by FastAPI)
│
├── ski/
│   ├── processing/         SessionProcessor pipeline orchestration
│   ├── analysis/           TurnAnalyzer, TurnInsights, TurnSignature
│   ├── metadata/           MetadataLoader
│   └── profiles/           YAML skier + ski profiles
│
├── features/modules/       Pluggable feature modules (pelvis, carving)
├── transformations/        Core pipeline functions
├── data/                   SQLite database, database.py
├── sessions/               raw/ processed/ plots/ (artifact storage)
├── tests/                  160 tests
├── docs/                   Architecture, API, vision, launch plan
└── logs/                   api.log, worker.log
```

## How to Run

### Prerequisites

- Python 3.12+
- Node.js 18+
- Redis

### Development (4 terminals)

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Worker
rq worker ski-pipeline

# Terminal 3: Backend
uvicorn backend.app:app --reload --port 8000

# Terminal 4: Frontend dev server
cd frontend && npm run dev
```

Open `http://localhost:5173` to upload and analyze sessions.

### Production build

```bash
cd frontend && npm run build
uvicorn backend.app:app --port 8000
```

The built React app is served from `/` by FastAPI. API lives at `/api/*`.

### Tests

```bash
python3 -m pytest tests/ -v
```

## Configuration

All backend config uses environment variables with sensible defaults.
See `backend/config.py` for the full list.

Key variables: `RAW_DIR`, `PROCESSED_DIR`, `PLOTS_DIR`, `REDIS_URL`,
`MAX_UPLOAD_MB`, `STORAGE_MODE`.

## Movement Scores

The system produces six biomechanical scores (0-1 scale) based on the
PSIA Five Fundamentals of Alpine Skiing plus Turn Rhythm:

| Score | What It Measures |
|-------|-----------------|
| Rotary Stability | How quiet the upper body stays during turns |
| Edge Consistency | Consistency of turn radius and edge engagement |
| Pressure Management | Efficiency of ski loading (centripetal force ratio) |
| Turn Symmetry | Left/right balance in turn shape and radius |
| Turn Shape Consistency | How repeatable the turn shape is across runs |
| Turn Rhythm | Regularity of turn timing / cadence |

Physics-based normalization (pressure ratio, torso rotation ratio,
ski-length normalized radius) enables cross-skier and cross-equipment
comparison.

## What's Next

Per the two-week launch plan (`docs/two-week-launch-plan.md`):

- **Day 7:** Polish the upload page (drag-and-drop, mobile-friendly, session history)
- **Day 8-9:** Results dashboard (score cards, GPS map, detailed metrics)
- **Day 10-11:** Mobile responsive, session comparison
- **Day 12-14:** Deploy to EC2 with Nginx, domain, SSL
