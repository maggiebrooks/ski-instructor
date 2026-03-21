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

# Install Python deps
pip install -r requirements.txt
pip install fastapi uvicorn redis rq python-multipart

# Install frontend deps
cd frontend && npm install && cd ..

# Start everything (4 terminals)
redis-server                                    # Terminal 1
rq worker ski-pipeline                          # Terminal 2
uvicorn backend.app:app --reload --port 8000    # Terminal 3
cd frontend && npm run dev                      # Terminal 4
```

Open `http://localhost:5173`. Upload a Sensor Logger `.zip` and watch the
results appear.

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
session comparison, EC2 deployment.
