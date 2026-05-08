# Ski Recorder

**Sensor-based ski analytics platform that turns iPhone IMU data into biomechanical technique scores.**

A skier records a run using the iOS app. The app captures accelerometer, gyroscope, barometer, and GPS data at up to 100 Hz. That session uploads to a FastAPI backend, moves through a signal processing pipeline, and produces scored feedback across seven movement dimensions aligned with PSIA instructor methodology — in about 60 seconds.

**Live demo:** https://ski-instructor.vercel.app — includes a sample session download if you want to see the full pipeline run end to end.

---

## What it does

Raw IMU data from a phone in a jacket pocket isn't useful on its own. The pipeline does several things to make it meaningful:

- **Butterworth low-pass filtering** removes high-frequency noise from the accelerometer and gyroscope signals
- **Madgwick sensor fusion** combines gyroscope and accelerometer readings into stable orientation estimates
- **Turn segmentation** identifies individual turns from the altitude and orientation signal, producing a labeled turn sequence for the full run
- **Feature extraction** computes per-turn physics quantities: centripetal force ratio, torso rotation ratio, ski-length-normalized turn radius, edge build rate, and timing intervals
- **Biomechanical scoring** maps those features to seven movement scores using physics-based normalization, enabling cross-skier and cross-equipment comparison

The seven scored dimensions:

| Score | What it measures |
|---|---|
| Rotary Stability | Upper body quiet during turns |
| Edge Consistency | Clean, consistent ski grip through each arc |
| Pressure Management | Loading and releasing the ski through the turn |
| Turn Symmetry | Left/right balance in shape and radius |
| Turn Shape Consistency | Repeatability of turn arcs across a run |
| Turn Rhythm | Consistency of timing between turns |
| Turn Efficiency | Speed carried through turns vs. scrubbed off |

Results include an overall score, per-dimension breakdowns with progress bars, turn signature visualization, coaching notes keyed to low-scoring dimensions, and a stats panel (turn count, average radius, g-force, speed).

---

## Stack

| Layer | Technology |
|---|---|
| Mobile | Expo React Native (iOS) — IMU + GPS recording |
| Frontend | React 19 + Vite + TypeScript |
| Backend | FastAPI (Python) |
| Job queue | RQ + Redis |
| Database | SQLite → PostgreSQL migration planned Nov 2026 |
| Deployment | Vercel (frontend) · Render (backend + worker) |
| Signal processing | NumPy · SciPy · Pandas |
| Testing | pytest — 160 tests |

---

## Architecture

```
iPhone (Expo RN)
    │  ZIP of CSVs (accel, gyro, baro, GPS)
    ▼
POST /api/upload-session
    │  preflight validation + dedup
    ▼
Redis / RQ job queue
    ▼
Worker: transformations/process_session.py
    ├── Butterworth filter
    ├── Madgwick fusion → orientation
    ├── Turn segmentation
    ├── Feature extraction (pelvis_turn_module, carving_phase_module)
    └── Biomechanical scoring → session report JSON
    ▼
GET /api/session/{id}  (polled by frontend until complete)
    ▼
React results dashboard
```

---

## Project status and roadmap

This is an active solo build. Current state:

- Full pipeline working end to end with real session data
- 160 unit tests across pipeline, analytics, scoring, and metadata
- Deployed and publicly accessible (demo mode — sample data only)
- Physics-based normalization validated on real runs

**Months 1–6 (now):** Infrastructure polish, PostgreSQL migration, auth layer, Render deployment stability

**Months 7–12:** Closed beta with ~30 skiers across ability levels. Collecting labeled ground truth data.

**Months 13–18:** Train ML models on labeled beta data to replace rule-based heuristics. App Store submission.

The rule-based scoring is intentionally conservative — it's designed to produce defensible results on limited data while the labeled dataset is being built. Accuracy integrity is the top priority; the ML layer doesn't ship until there's enough real data to validate it properly.

---

## Known limitations

- **Single sensor placement** (belly/front jacket pocket). Dual-sensor setup (chest + boot) would unlock upper/lower body separation, which is the next hardware iteration.
- **Turn detection parameters** (`height=0.5`, `distance=20`) are starting values tuned for groomed intermediate terrain. Per-terrain calibration is on the roadmap.
- **Phone placement variance** — jacket movement introduces noise. The Butterworth filter attenuates most of it but placement consistency matters, which is why phone placement is standardized in the recording protocol.
- **Altitude-only segmentation** — adding gyroscope + speed confirmation would improve turn boundary accuracy on flat or variable terrain.

---

## Running locally

**Prerequisites:** Python 3.12+, Node.js 18+, Redis

```bash
# Clone and install
git clone https://github.com/maggiebrooks/ski-ai
cd ski-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Start everything (API + worker + frontend + Redis)
./scripts/dev.sh
```

Open http://localhost:5173. API docs at http://localhost:8000/api/docs.

Upload a Sensor Logger `.zip` or use the sample session from the live demo.

---

## Tests

```bash
python -m pytest tests/ -v
```

160 tests covering the pipeline, turn analytics, biomechanical scoring, feature modules, and metadata loading.

---

## Built by

Maggie Brooks — full-stack engineer, PSIA Level 1 ski instructor, former Team USA synchronized figure skater.

The project came from a real problem: ski instruction is almost entirely visual and verbal, with no objective data layer. Ski Recorder is an attempt to build that data layer in a way that complements coaching rather than replacing it.

[maggiebrooks.com](https://maggiebrooks.com) · [LinkedIn](https://linkedin.com/in/maggiebrooks)
