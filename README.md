# Ski Recorder

**Sensor-based ski analytics platform that turns iPhone IMU data into biomechanical technique scores.**

A skier records a run using the iOS app. The app captures accelerometer, gyroscope, barometer, and GPS data at up to 100 Hz. That session uploads to a FastAPI backend, moves through a signal processing pipeline, and produces scored feedback across seven movement dimensions aligned with PSIA instructor methodology in about 60 seconds.

**Live demo:** https://ski-instructor.vercel.app. It includes a sample session download if you want to see the full pipeline run end to end.

---

## What it does

Raw IMU data from a phone in a jacket pocket isn't useful on its own. The pipeline does several things to make it meaningful:

- **Body-frame alignment**: before any metrics are computed, raw sensor-frame accelerometer and gyroscope readings are rotated into a gravity-aligned body frame using a Rodrigues rotation matrix (`ski/frame_alignment.py`). The gravity vector is estimated from the lowest-motion window in the session (typically a chairlift ride). This ensures gyroscope yaw rate maps to the skier's actual turn axis regardless of how the phone sits in the pocket, and that accelerometer magnitude reflects dynamic loading rather than a mix of loading and gravity.
- **Butterworth low-pass filtering**: 4th-order zero-phase filter at 5 Hz (matching Elfmark et al. 2021) removes high-frequency noise before feature extraction. Zero-phase (`sosfiltfilt`) avoids the group delay a causal filter would introduce into turn timing metrics.
- **Barometric run segmentation**: a rolling-window altitude rate classifier labels each row as skiing, chairlift, or idle. Short segments below 30 seconds are merged into neighbors to suppress classification flicker. If no barometer data is present, the full session is treated as one skiing run.
- **Turn detection**: `scipy.signal.find_peaks` on the absolute body-frame gyroscope yaw signal. Turns are sliced at midpoints between peaks, giving one DataFrame per turn for feature extraction.
- **Feature extraction**: two modules run per turn: `PelvisTurnModule` computes integrated turn angle, peak rotation rate, estimated radius (speed / yaw rate), roll range, peak g-force, and timing symmetry. `CarvingPhaseModule` computes edge build progressiveness, radius stability, and speed loss across initiation / apex / finish phases.
- **Biomechanical scoring**: seven scores in [0, 1] derived from per-turn features using physics-based formulas. Turn radius is normalized by ski sidecut radius; g-force is expressed as a centripetal ratio rather than absolute magnitude, making scores comparable across different skiers and equipment.
- **Per-metric confidence scoring**: each score is weighted by data quality signals (GPS fix accuracy, IMU sampling rate stability, gyroscope SNR, data completeness). A score from a noisy or incomplete session surfaces with lower confidence rather than being silently presented as authoritative.

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

Results include an overall score, per-dimension breakdowns with progress bars, coaching notes keyed to low-scoring dimensions, and a stats panel (turn count, vertical drop, max speed, average radius, turns per minute).

---

## Stack

| Layer | Technology |
|---|---|
| Mobile | Expo React Native (iOS): IMU + GPS recording |
| Frontend | React 19 + Vite + TypeScript |
| Backend | FastAPI (Python) |
| Job queue | RQ + Redis |
| Database | SQLite → PostgreSQL migration planned before beta |
| Deployment | Vercel (frontend) · Render (backend + worker) |
| Signal processing | NumPy · SciPy · Pandas |
| Testing | pytest · 229 tests |

---

## Architecture

```
iPhone (Expo RN)
    │  ZIP of CSVs (Accelerometer, Gyroscope, Barometer, Location)
    │  + session_metadata.json (phone_placement, session_quality)
    ▼
POST /api/upload-session
    │  size check · ZIP validation · SHA-256 dedup · preflight row/duration bounds
    ▼
Redis / RQ job queue
    ▼
Worker: ski/processing/session_processor.py
    ├── load_session()           : inner-join accel+gyro, merge_asof secondaries
    ├── preprocess()             : Butterworth filter, 100 → 20 Hz downsample
    ├── align_session()          : gravity rotation matrix (ski/frame_alignment.py)
    ├── segment_runs()           : barometric altitude rate classifier
    ├── detect_turns_by_run()    : gyroscope peak detection per skiing run
    ├── PelvisTurnModule         : angle, radius, g-force, symmetry per turn
    ├── CarvingPhaseModule       : edge build rate, phase timing per turn
    ├── compute_movement_scores(): 7 PSIA scores [0, 1]
    └── confidence weighting     : per-metric quality signals
    ▼
GET /api/session/{id}   (polled by frontend until status = complete)
    ▼
React results dashboard
```

---

## Known limitations

- **Single sensor placement.** The current protocol uses one phone in a jacket pocket. A dual-sensor setup (thigh + chest) would unlock upper/lower body separation: the difference between the femur driving the turn and the torso staying quiet is one of the most important PSIA fundamentals and is currently undetectable with one sensor. Phone placement (`femur` / `chest`) is already tracked per session in the database in preparation for this.
- **Turn detection parameters** (`height=0.5 rad/s`, `distance=20 samples`) are starting values tuned for groomed intermediate terrain. Bumps, steep chutes, and variable snow compress or exaggerate yaw rates in ways the current thresholds don't account for. Per-terrain calibration is on the roadmap.
- **Phone placement variance.** Jacket movement introduces noise the Butterworth filter doesn't fully attenuate. Placement consistency matters, which is why the recording protocol standardizes it and the app enforces portrait orientation at runtime.
- **Pressure ratio not yet field-validated.** The pressure management score uses centripetal physics as a proxy for actual ski loading. The diagnostic pipeline (`compute_pressure_ratio_diagnostics`) is built and running in the worker; surfacing that output and validating the zone bands against known-good carving sessions is the immediate next step.
- **Edge angle is estimated, not measured.** Roll angle from hip motion is a proxy for ski edge angle. A boot-mounted sensor would give a direct measurement; the current single-phone setup approximates it from the pelvis IMU.

---

## Project status

**Early preview: active development.**

The analysis pipeline is working end-to-end. The iOS app and full user accounts are targeting a **closed beta for winter 2026-2027** and an **App Store release for 2027-2028**.

What's working:
- Full signal processing pipeline (ingest → scores)
- Body-frame IMU alignment via gravity-estimated rotation matrix
- Seven PSIA movement scores with per-score coaching cues
- Web demo with sample session upload
- Per-metric confidence scoring
- Phone placement metadata tracked end-to-end (picker → ZIP → pipeline → database)

---

## Immediate next steps

**Phase 2: Pressure ratio validation.** Surface `compute_pressure_ratio_diagnostics()` output in the API response and frontend. Validate zone bands against real sessions. Upgrade spec §3.1 from "proxy" to "validated."

**Phase 3: Column rename documentation.** An undocumented rename layer exists between feature module output keys (`pelvis_turn_angle_deg`) and database column names (`pelvis_integrated_turn_angle`). Extract it into a named constant dict before adding new feature modules.

**Phase 4: Metadata-driven normalization.** Wire `interpret_fundamentals(metadata=...)` to use ski geometry (sidecut radius) and skier weight for physics-based score normalization. Adjust frame alignment axis assumptions per `phone_placement`.

**Phase 5: Confidence system hardening.** Several confidence signals are stubs deferred until Phases 1 and 4 stabilize the underlying metrics: `_edge_angle_confidence` returns a literal `0.5`, `_symmetry_confidence` uses undocumented step values, GPS quality is pessimistically scored for IMU-only sessions, and `missing_ratio` is misnamed (it's a presence ratio).

**Phase 6: Spec hygiene.** Keep [`docs/math.md`](docs/math.md) aligned with formulas and assumptions referenced from `confidence.py` and the live pipeline. Replace stale line-number citations in `algorithm-spec.md` with function names. Document `pressure_management` partial-input fallback behavior.

**SQLite → PostgreSQL migration.** Required before beta for concurrent users on Render's persistent storage model.

---

## Running locally

**Prerequisites:** Python 3.12+, Node.js 18+, Redis

```bash
git clone https://github.com/maggiebrooks/ski-ai
cd ski-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Start API + worker + frontend
./scripts/dev.sh
```

Open http://localhost:5173. API docs at http://localhost:8000/api/docs.

Upload a Sensor Logger `.zip` or use the sample session from the live demo.

---

## Tests

```bash
python -m pytest tests/ -v
```

229 tests covering the signal processing pipeline, turn analytics, biomechanical scoring, feature modules, frame alignment, and metadata loading.

---

## Algorithm documentation

Full algorithm specification, scoring formulas, signal processing decisions, and inline literature citations (Elfmark 2021, Tang 2024, and others) are in [`docs/algorithm-spec.md`](docs/algorithm-spec.md).

---

## Built by

Maggie Brooks, full-stack engineer, PSIA Level 1 ski instructor, former Team USA synchronized figure skater.

The project came from a real problem: ski instruction is almost entirely visual and verbal, with no objective data layer. Ski Recorder is an attempt to build that data layer in a way that complements coaching rather than replacing it.

[maggie-brooks.com](https://maggie-brooks.com) · [LinkedIn](https://www.linkedin.com/in/maggie-margaret-brooks-6017601b6/)
