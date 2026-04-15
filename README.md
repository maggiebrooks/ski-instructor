# ski-ai

Sensor-based ski analytics platform. Records IMU and GPS data with
[Sensor Logger](https://www.tszheichoi.com/sensorlogger) on an iPhone,
uploads via a web UI, and produces biomechanical feedback scored against the
PSIA Five Fundamentals of Alpine Skiing.

**Status:** Full-stack web application with FastAPI backend, React frontend,
Redis job queue, and 160 unit tests. Six biomechanical movement scores with
physics-based normalization, turn signature visualization, and session
comparison. Processing version 2.0.0.

---

## Quick Start

### Run the full stack (development)

```bash
# Prerequisites: Python 3.12+, Node.js 18+, Redis

# From repository root — activate the virtualenv you already use, e.g.:
#   source venv/bin/activate
#   source .venv/bin/activate
# (Windows: venv\Scripts\activate). Create one first only if you do not have one:
#   python3 -m venv venv

# Install Python deps
python -m pip install -r requirements.txt
python -m pip install fastapi uvicorn redis rq python-multipart honcho

# Install frontend deps
cd frontend && npm install && cd ..

# Start everything — pick one:

# Option A — one terminal (Honcho runs API + worker + Vite; venv must be active)
# Requires Redis on localhost:6379 (often already running via Homebrew/Docker).
honcho start
# If you see "Address already in use" for 6379, Redis is already up — use `honcho start` only (default Procfile).
# If Redis is not running and port 6379 is free: honcho -f Procfile.with-redis start

# Option B — four terminals (activate your venv in each that runs Python)
# Skip redis-server if Redis is already running on 6379.
redis-server
python -m backend.rq_render_worker
uvicorn backend.app:app --reload --port 8000
cd frontend && npm run dev
```

From the **repository root**, with your usual virtualenv activated (so `python`,
`pip`, and `honcho` resolve inside that env). If you skip activation, call
`venv/bin/python` and `venv/bin/honcho` using **your** venv directory name.
Install `frontend` dependencies once (`cd frontend && npm install`). Honcho
reads [`Procfile`](Procfile) (API, RQ worker, Vite). Redis is started separately unless you use [`Procfile.with-redis`](Procfile.with-redis).

Open `http://localhost:5173`. API docs: `http://localhost:8000/api/docs`.
Upload a Sensor Logger `.zip` and watch the results appear.

**Railway** (`ski-ai-api`, `ski-ai-worker`, Redis) is for **production** only.
For local dev you still run Redis + API + worker on your machine (or point
`REDIS_URL` at a tunnel — not required for typical setup).

### Docker (API + worker, Render-compatible)

Build from the **repository root** (the image needs `ski/`, `data/`, `features/`, `transformations/`, not only `backend/`):

```bash
docker build -f backend/Dockerfile -t ski-ai-backend .
docker run --rm -p 10000:10000 -e REDIS_URL=redis://host.docker.internal:6379 ski-ai-backend
```

- Swagger UI: `http://localhost:10000/api/docs` (API is mounted under `/api`).
- RQ worker (same image, separate container/process):  
  `python -m backend.rq_render_worker`  
  Uses queue name `ski-pipeline` and `REDIS_URL` from the environment.
- Optional Blueprint: [`render.yaml`](render.yaml).
- If `docker build` fails during `apt-get` with **Hash Sum mismatch**, retry the build (mirror glitch) or ensure the Dockerfile uses a pinned base like `python:3.11-slim-bookworm`. If `pip install` later fails compiling a package, add `build-essential` back in the Dockerfile.

### Run the pipeline directly (no server)

```bash
python main.py
```

### Run tests

```bash
python -m pytest tests/ -v    # 160 tests
```

---

## Deployment

This project uses **[Railway](https://railway.app/)** for the backend API, background worker, and Redis.

### Services

| Service | Role |
|---------|------|
| **ski-ai-api** | FastAPI (`uvicorn backend.app:app`) |
| **ski-ai-worker** | RQ worker processing the `ski-pipeline` queue |
| **Redis** | Managed via Railway Redis (or compatible add-on) |

### Environment variables

| Variable | Notes |
|----------|--------|
| **`REDIS_URL`** | Redis connection string — **required on both the API and the worker**. Same value on both services. |

If `REDIS_URL` is missing on either service, uploads may fail to enqueue or jobs may never run.

### Running locally

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — API
uvicorn backend.app:app --reload --port 8000

# Terminal 3 — Worker (from repository root; uses `REDIS_URL` or defaults to localhost)
python -m backend.rq_render_worker

# Terminal 4 — Frontend (optional)
cd frontend && npm run dev
```

### Accessing the API

| | Path |
|---|------|
| **Swagger UI** | `/api/docs` |
| **OpenAPI JSON** | `/api/openapi.json` |

Example endpoints:

- `POST /api/upload-session`
- `GET /api/session/{id}`
- `DELETE /api/session/{id}`

On Railway, open **`https://<your-api-host>/api/docs`** (e.g. `https://ski-ai-api-production.up.railway.app/api/docs` if that matches your service URL).

**Tips**

- Use **`/api/docs`**, not `/docs` on the root app — REST routes are mounted under `/api`, so Swagger lives on the API sub-app.
- Ensure the **worker** service has **`REDIS_URL`**, not only the web API.

---

## Frontend deployment (MVP)

**Goal:** Ship the upload UI and session pages on a public URL, talking to the live Railway API.

| Option | Notes |
|--------|--------|
| **Vercel** (recommended for MVP) | React + Vite deploys easily; free tier; set one env var for the API base. |
| **Railway** | Possible to Dockerize or static-serve the frontend; more moving parts than Vercel for a Vite SPA. |

**MVP path**

1. Keep **API + worker + Redis** on Railway.
2. Deploy **`frontend/`** on **Vercel** (or similar static host).
3. Set **`VITE_API_BASE_URL`** to your Railway API **including `/api`** (see below).

### Vercel (suggested steps)

1. Push the repo to GitHub (if it is not already).
2. Vercel → **Add New** → **Project** → import the repo; set the **root directory** to `frontend` if Vercel should only build the SPA.
3. **Environment variable** (Production — adjust host to your Railway URL):

   ```bash
   VITE_API_BASE_URL=https://ski-ai-api-production.up.railway.app/api
   ```

   Axios uses paths like `/upload-session`; `baseURL` must be the API prefix **`.../api`**, not only the origin.

4. Build and deploy, then test upload and session pages against production.

---

## Documentation

| Document | Contents |
|----------|----------|
| [Project Status](docs/project-status.md) | Current state, architecture diagram, what's built, what's next |
| [API Reference](docs/api.md) | HTTP endpoints, storage layer, job tracking, pipeline API, analytics API |
| [Architecture](docs/architecture.md) | Pipeline diagram, 8 systems, data hierarchy, scoring, feature modules, roadmap |
| [Two-Week Launch Plan](docs/two-week-launch-plan.md) | Web deployment execution plan with daily milestones |
| [Vision](docs/vision.md) | Product vision, principles, why ski-ai |
| [Data](docs/data.md) | Sensor Logger source files, output schema |
| [Configuration](docs/configuration.md) | Pipeline parameters, database schema |
| [Metadata](docs/metadata.md) | Skier/ski profiles, session metadata, MetadataLoader |
| [Testing](docs/testing.md) | Test suite overview |
| [GitHub setup](docs/github-setup.md) | Private repo, SSH, `.gitignore`, secrets |

---

## Project Structure

```
ski-ai/
├── backend/                         # FastAPI server
│   ├── app.py                       # App setup, CORS, static mount, routes
│   ├── config.py                    # Env-based config (dirs, Redis, upload limit)
│   ├── models.py                    # Jobs table + hash dedup
│   ├── storage.py                   # Storage abstraction (local → S3)
│   ├── worker.py                    # RQ worker: pipeline + artifact writes
│   └── routes/
│       ├── upload.py                # POST /api/upload-session
│       ├── sessions.py              # GET status, list, plots
│       └── metadata.py              # GET session metadata
│
├── frontend/                        # React + Vite
│   ├── src/
│   │   ├── App.tsx                  # Router (/, /session/:id)
│   │   ├── api.ts                   # Axios helpers
│   │   ├── pages/Upload.tsx         # Upload page
│   │   ├── pages/Session.tsx        # Processing + results page
│   │   └── components/Progress.tsx  # Pipeline progress indicator
│   └── vite.config.ts               # Dev proxy /api → :8000
│
├── ski/                             # Core analytics package
│   ├── processing/session_processor.py  # Pipeline orchestration
│   ├── analysis/turn_analyzer.py        # DB-backed analytics
│   ├── analysis/turn_insights.py        # Biomechanical scoring
│   ├── analysis/turn_signature.py       # Turn curve visualization
│   └── metadata/metadata_loader.py      # YAML profile loader
│
├── features/modules/                # Pluggable feature extraction
│   ├── pelvis_turn_module.py        # Turn physics (angle, radius, g-force)
│   └── carving_phase_module.py      # Phase detection + carving metrics
│
├── transformations/process_session.py  # Core pipeline functions
├── data/                            # SQLite database
├── sessions/                        # raw/ processed/ plots/
├── tests/                           # 160 tests across 5 files
├── docs/                            # Documentation
└── logs/                            # api.log, worker.log
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload-session` | Upload ZIP, validate, dedup, enqueue |
| `GET` | `/api/session/{id}` | Status + report (poll during processing) |
| `GET` | `/api/sessions` | List completed sessions |
| `GET` | `/api/session/{id}/plot/{name}` | Serve plot PNGs |
| `GET` | `/api/session/{id}/metadata` | Skier/ski/session metadata |
| `GET` | `/api/health` | Health check |

See [docs/api.md](docs/api.md) for request/response details.

---

## Movement Scores

Six biomechanical scores (0-1) based on the PSIA Five Fundamentals:

| Score | Signal |
|-------|--------|
| Rotary Stability | Upper body quiet during turns (torso rotation ratio) |
| Edge Consistency | Turn radius CV, edge build, radius stability |
| Pressure Management | Ski loading efficiency (centripetal force ratio) |
| Turn Symmetry | Left/right balance in shape and radius |
| Turn Shape Consistency | Repeatability of turn radius and angle |
| Turn Rhythm | Regularity of turn timing |

Physics-based normalization enables cross-skier and cross-equipment
comparison via pressure ratio, torso rotation ratio, and ski-length
normalized radius.

---

## Known Limitations

1. Turn detection parameters (`height=0.5`, `distance=20`) are starting
   values and should be tuned per-terrain.
2. Single-sensor only (pelvis phone). Dual-phone (chest + boot) would
   unlock upper/lower body separation metrics.
3. Processed CSVs are large. Parquet output planned.
4. Segmentation uses altitude only. Gyro + speed would improve accuracy.

---

## Roadmap

See [docs/two-week-launch-plan.md](docs/two-week-launch-plan.md) for the
active deployment plan and [docs/architecture.md](docs/architecture.md)
for the long-term vision.

**Completed:** Pipeline, feature modules, biomechanical scoring,
physics-based normalization, turn signatures, metadata system, backend API,
storage abstraction, React frontend skeleton, job tracking, dedup, logging.

**Next:** Upload page polish, results dashboard, GPS map, mobile responsive,
session comparison, frontend on Vercel (see [Frontend deployment (MVP)](#frontend-deployment-mvp)).
