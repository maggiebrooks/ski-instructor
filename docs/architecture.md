# ski-ai — System Architecture

## Current System

Data flows top-to-bottom through seven major layers. The `SessionProcessor`
class (`ski/processing/session_processor.py`) orchestrates steps 1-6 as a
single reusable method call.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA CAPTURE                                 │
│                                                                     │
│   iPhone (belly pocket)  ──►  Sensor Logger App  ──►  CSV Export    │
│   • Accelerometer 100Hz        8 sensor files          per session  │
│   • Gyroscope 100Hz            per recording                        │
│   • GPS ~1Hz                                                        │
│   • Barometer ~1Hz                                                  │
│   • Orientation 100Hz                                               │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
╔═════════════════════════════════════════════════════════════════════╗
║         ORCHESTRATION  (SessionProcessor.process())                ║
╠═════════════════════════════════════════════════════════════════════╣
║                                                                     ║
║  Callers:  CLI (__main__)  │  main.py  │  Future API / notebook     ║
║                                                                     ║
╚════════════════════════════════╤════════════════════════════════════╝
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       1. INGESTION                                  │
│                                                                     │
│   Multi-file CSV loader  →  Inner join IMU  →  merge_asof GPS/Baro │
│   Result: single unified DataFrame, ~100 Hz, 24 columns             │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     2. PREPROCESSING                                │
│                                                                     │
│   Timestamp normalization  →  Butterworth LP filter (5 Hz, order 2) │
│   →  Downsample 100 Hz → 20 Hz                                     │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     3. SEGMENTATION                                 │
│                                                                     │
│   Altitude-rate classification:  skiing │ lift │ idle                │
│   Assigns run_id to each contiguous skiing block                    │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    4. TURN DETECTION                                │
│                                                                     │
│   Per-run peak detection on |gyro_z|  (scipy find_peaks)            │
│   Segments DataFrame into per-turn slices                           │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  5. FEATURE MODULES                                 │
│                  (pluggable system)                                  │
│                                                                     │
│  ┌──────────────────────┐   ┌───────────────────────┐               │
│  │  PelvisTurnModule    │   │  CarvingPhaseModule   │               │
│  │                      │   │                       │               │
│  │  • turn angle        │   │  • phase detection    │               │
│  │  • rotation rate     │   │    (init/apex/finish)  │               │
│  │  • turn radius       │   │  • edge build slope   │               │
│  │  • roll angle range  │   │  • radius stability   │               │
│  │  • g-force           │   │  • speed loss ratio   │               │
│  │  • symmetry          │   │                       │               │
│  └──────────────────────┘   └───────────────────────┘               │
│                                                                     │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐   ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐               │
│    FatigueModule             BootIMUModule                          │
│    (future)                  (future)                               │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘   └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘               │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      6. OUTPUT LAYER                                │
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│   │   JSON   │    │   CSV    │    │  SQLite  │    │   PNG    │     │
│   │ summaries│    │processed │    │  ski.db  │    │  5-panel │     │
│   │per-session│   │ datasets │    │ 3 tables │    │  plots   │     │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘     │
│                                                                     │
│   sessions ──► runs ──► turns   (hierarchical, all three stores)    │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    7. ANALYTICS (read path)                         │
│                                                                     │
│   TurnAnalyzer   ─── load_turns() ──► session_metrics()             │
│                                   └──► compare_sessions()           │
│                                                                     │
│   TurnInsights   ─── compute_normalized_metrics(df, metadata)       │
│                  ─── compute_movement_scores(df, metadata)          │
│                  ─── interpret_fundamentals(scores)                 │
│                  ─── session_report(analyzer, session_id, metadata) │
│                                                                     │
│   Turn signature ─── plot_session_signature(analyzer, session_id)   │
│                                                                     │
│   Physics-based normalization:                                      │
│     • pressure_ratio  = measured_g / centripetal_g                   │
│     • torso_rotation  = (ω × t) / |turn_angle|                     │
│     • normalized_radius = radius / ski_length  (needs metadata)     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    8. METADATA (side-car, feeds analytics)           │
│                                                                     │
│   MetadataLoader  ─── load_skier_profile("maggie")                  │
│                   ─── load_ski_profile("sheeva10_104_158")           │
│                   ─── load_session_metadata(session_path)           │
│                                                                     │
│   YAML-based profiles + per-session context.                        │
│   Consumed by TurnInsights for physics-based normalization          │
│   (ski length, future: skier weight, waist width).                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Eight Major Systems

| # | System | What It Does | Key Files |
|---|--------|-------------|-----------|
| **1** | **Ingestion** | Fuses 8 sensor CSVs into one time-aligned DataFrame | `process_session.py` (`load_session`) |
| **2** | **Preprocessing** | Filters noise, downsamples, segments skiing/lift/idle | `process_session.py` (`preprocess`, `segment_runs`) |
| **3** | **Analysis** | Detects turns, runs pluggable feature modules, computes per-turn/run/session metrics | `features/modules/`, `process_session.py` |
| **4** | **Storage** | SQLite database (sessions/runs/turns) + JSON summaries + processed CSVs | `data/database.py`, `data/ski.db` |
| **5** | **Visualization** | 5-panel session PNGs with activity shading and turn markers | `process_session.py` (`plot_session`) |
| **6** | **Orchestration** | Reusable `SessionProcessor` class encapsulating the full pipeline; called by CLI, `main.py`, and future APIs/notebooks | `ski/processing/session_processor.py` |
| **7** | **Analytics** | Read-only `TurnAnalyzer` for post-hoc DB queries, per-session metrics, and cross-session comparison; `TurnInsights` for 6 biomechanical movement scores with physics-based normalization (centripetal pressure ratio, torso rotation ratio, ski-length normalized radius) and Five-Fundamentals + Turn Rhythm feedback; `TurnSignature` for median turn curve visualization | `ski/analysis/turn_analyzer.py`, `ski/analysis/turn_insights.py`, `ski/analysis/turn_signature.py` |
| **8** | **Metadata** | YAML-based skier profiles, ski equipment profiles, and per-session context; consumed by `TurnInsights` normalization layer for cross-skier/equipment comparison | `ski/metadata/metadata_loader.py`, `ski/profiles/`, `scripts/add_metadata.py` |

---

## Data Hierarchy

```
Session
├── session_id, date, duration, total_vertical, schema_version
│
├── Run 1
│   ├── run_id, duration, vertical, speed, turn count
│   │
│   ├── Turn 1
│   │   ├── sensor_source: "pelvis_phone"
│   │   ├── direction, duration, speed_at_apex
│   │   ├── pelvis_turn_angle, pelvis_rotation_rate, pelvis_turn_radius
│   │   ├── pelvis_max_roll_angle, pelvis_g_force, pelvis_symmetry
│   │   ├── phase: initiation → apex → finish
│   │   └── pelvis_edge_build, pelvis_radius_stability, speed_loss
│   │
│   ├── Turn 2 ...
│   └── Turn N ...
│
├── Run 2 ...
└── Run N ...
```

---

## Consumer Product Evolution

Each layer maps to a today/future progression.

```
┌─────────────────────────────────────────────────────────────────────┐
│  CAPTURE LAYER          Today              Future                    │
│                         ─────              ──────                    │
│                         Phone in pocket    Dual phone: chest + boot  │
│                         Manual CSV export  Auto-sync via BLE/WiFi    │
│                         Sensor Logger app  Custom iOS/Android app    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PROCESSING LAYER       Today              Future                    │
│                         ─────              ──────                    │
│                         Local Python CLI   Cloud pipeline            │
│                         Batch processing   Real-time streaming       │
│                         Single machine     Serverless (Lambda/GCF)   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ANALYTICS LAYER        Today              Future                    │
│                         ─────              ──────                    │
│                         Deterministic      Deterministic + ML        │
│                         physics metrics    Turn quality scoring      │
│                         Pelvis sensor      Dual-sensor: upper/lower  │
│                         6 movement scores    body separation metrics │
│                         Physics-based      Style classification      │
│                           normalization    Fatigue detection         │
│                         Turn signature     Terrain-aware scoring     │
│                           visualization                              │
│                         Feature modules                              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STORAGE LAYER          Today              Future                    │
│                         ─────              ──────                    │
│                         Local SQLite       Postgres / cloud DB       │
│                         JSON files         API-served data           │
│                         Schema v2.0.0      User accounts + history   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER     Today              Future                    │
│                         ─────              ──────                    │
│                         Static PNGs        Mobile app dashboard      │
│                         Raw SQL queries    3D animated slope replay  │
│                         JSON inspection    Social / coach sharing    │
│                                            Push notifications        │
│                                            Leaderboards              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## What's Built vs. What's Next

| Layer | Built | Next Step |
|-------|-------|-----------|
| Capture | Single phone (chest), manual export | Dual phone (chest + boot cuff) for upper/lower body separation, auto-sync |
| Processing | `SessionProcessor` orchestration class, full batch pipeline, 20 Hz | Streaming / on-device edge processing |
| Analytics | 2 feature modules, 16 per-turn metrics, `TurnAnalyzer` read-back layer with cross-session comparison, `TurnInsights` 6 biomechanical scores with physics-based normalization (pressure ratio, torso rotation ratio, ski-length normalized radius), Five-Fundamentals + Turn Rhythm feedback, turn signature visualization | Dual-sensor separation metrics, carving quality score, then ML scoring |
| Metadata | YAML skier profiles, ski profiles, per-session metadata, `MetadataLoader`, interactive CLI (`scripts/add_metadata.py`), metadata consumed by `TurnInsights` normalization (ski length today) | Skier height/weight in normalization (weight-normalized g-force, body-size adjustments), terrain-aware scoring |
| Storage | SQLite + JSON, processing version 2.0.0 | Cloud DB, user profiles, API |
| Presentation | Static 5-panel PNGs, turn signature curves | Mobile dashboard, 3D animated slope replay |

---

## Biomechanical Scoring & Normalization

The `TurnInsights` class provides a three-tier analytics stack on top of
the raw per-turn data stored in SQLite:

```
Per-turn DB rows
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  compute_normalized_metrics(df, metadata)             │
│                                                       │
│  Physics-based dimensionless ratios:                  │
│  • pressure_ratio  = measured_g / expected_g          │
│    where expected_g = v² / (r × 9.81)                 │
│  • torso_rotation_ratio = (ω × t) / |turn_angle|     │
│  • normalized_turn_radius = radius / ski_length_m     │
│    (requires ski.length_cm from metadata)              │
│                                                       │
│  Median aggregation, NaN/inf cleaned, radius < 0.5    │
│  excluded. Returns None for unavailable metrics.      │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  compute_movement_scores(df, metadata)                │
│                                                       │
│  Six 0-1 scores:                                      │
│  1. rotary_stability     ← torso_rotation_ratio       │
│  2. edge_consistency     ← radius_cv, edge_build,     │
│                            radius_stability            │
│  3. pressure_management  ← pressure_ratio OR g/1.2    │
│                            + speed efficiency          │
│  4. turn_symmetry        ← L/R balance, symmetry,     │
│                            radius parity               │
│  5. turn_shape           ← radius_cv + angle_cv       │
│  6. turn_rhythm          ← 1 − duration_cv            │
│                                                       │
│  Also returns: turn_efficiency, normalized_turn_radius,│
│  pressure_ratio, torso_rotation_ratio                  │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  interpret_fundamentals(scores, metadata)             │
│                                                       │
│  Maps scores to PSIA Five Fundamentals feedback:      │
│  • Fore/Aft Balance    ← pressure_management          │
│  • Foot-to-Foot Balance← turn_symmetry                │
│  • Rotary Control      ← rotary_stability             │
│  • Edging Control      ← edge_consistency             │
│  • Pressure Control    ← pressure_management          │
│  • Turn Rhythm         ← turn_rhythm                  │
│                                                       │
│  Three-tier thresholds produce instructor-style text.  │
└──────────────────────────────────────────────────────┘
```

### Normalization Design

Physics-based normalization solves the problem of comparing skiers with
different body types and equipment. Without normalization, a 12 m turn
on 180 cm skis means something very different from 12 m on 148 cm skis.

- **`pressure_ratio`** uses centripetal force (v²/r) to compute the G-force
  a perfectly efficient carve would produce, then divides the measured
  G-force by that expected value. A ratio near 1.0 indicates efficient ski
  loading; below 0.6 suggests skidding or light pressure; above 1.2
  indicates aggressive loading.

- **`torso_rotation_ratio`** estimates how much the torso rotates relative
  to the ski's arc. A ratio below 0.3 indicates a quiet upper body; above
  0.7 indicates upper-body steering (common in intermediate skiers).

- **`normalized_turn_radius`** divides turn radius by ski length, producing
  a dimensionless number. Values below 5 indicate very tight turns; 5-8
  indicate carved GS-style turns; above 10 indicate long-radius cruising.

All metrics fall back gracefully when metadata is absent, using raw
heuristics (e.g., `g_force / 1.2`) to maintain backward compatibility.

---

## Feature Module Extension Point

The feature module system is the primary extension point for new analytics.
Adding a new feature family requires no pipeline changes:

```
features/modules/
├── base.py                     ◄── FeatureModule interface
├── pelvis_turn_module.py       ◄── ACTIVE (turn physics)
├── carving_phase_module.py     ◄── ACTIVE (carving analytics)
├── fatigue_module.py           ◄── future
├── boot_imu_module.py          ◄── future (second sensor)
├── terrain_module.py           ◄── future (GPS slope analysis)
└── style_module.py             ◄── future (carve vs skid classification)
```

Each module implements `compute(turn_df, context) -> dict` and is
registered in `ACTIVE_FEATURE_MODULES` inside `process_session.py`.

---

## Future Roadmap

### Dual-Phone Sensors (highest-impact hardware change)

Mount a second phone at the boot cuff while keeping the chest phone in place.
This enables measurement of **upper-body vs. lower-body separation** —
widely regarded as the single most important biomechanical indicator in
advanced skiing.

**What it unlocks:**

| Signal | Source |
|--------|--------|
| Hip angulation vs. torso angle | Chest – Boot differential in roll |
| Knee/ankle steering vs. upper body quiet | Boot gyro_z vs. chest gyro_z |
| Edge angle at the ski | Boot roll angle |
| Lower-body rotary independence | Boot yaw rate minus chest yaw rate |

**Implementation path:**

1. Record both phones simultaneously via Sensor Logger (already supports
   multi-device export).
2. Add a `BootIMUModule` feature module — no pipeline changes needed.
3. Time-align the two streams using existing `merge_asof` infrastructure.
4. Compute differential metrics (e.g., `separation_angle = boot_roll - chest_roll`).
5. Feed separation scores into `TurnInsights` as a new fundamental dimension.

### 3D Animated Slope Replay

Render a 3D visualization of the skier descending the slope, reconstructed
from GPS track + orientation + turn metrics.

**Concept:**

- GPS lat/lon/alt trace defines the path down the mountain.
- Orientation quaternions (or yaw/pitch/roll) animate a simplified skier model.
- Turn boundaries and phase markers (initiation/apex/finish) can be
  color-coded along the path.
- Camera can follow the skier or orbit freely.

**Tech options:**

| Approach | Pros | Cons |
|----------|------|------|
| Three.js (web) | Runs anywhere, shareable link | Requires web frontend |
| Blender Python scripting | High-quality renders, offline | Batch only |
| Unity/Unreal | Real-time, AR-ready | Heavy toolchain |
| Matplotlib 3D + animation | Quick prototype, no new deps | Limited quality |

**Recommended first step:** Prototype with Three.js using the GPS track +
interpolated orientation exported to GeoJSON/glTF, then layer in the
biomechanical annotations once the renderer is stable.
