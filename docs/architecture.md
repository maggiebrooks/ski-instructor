# ski-ai: System Architecture

## Current System

Data flows top-to-bottom through seven major layers. The `SessionProcessor`
class (`ski/processing/session_processor.py`) orchestrates steps 1-6 as a
single reusable method call.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA CAPTURE                                 │
│                                                                     │
│   iPhone (thigh pocket) ──►  Mobile app (preferred)  ──►  ZIP upload │
│   • Accelerometer 100 Hz       4 CSVs at top-level                   │
│   • Gyroscope 100 Hz           (Accel/Gyro/GPS/Baro)                 │
│   • GPS ~1 Hz                                                      │
│   • Barometer ~1 Hz                                                │
│   (Sensor Logger exports are still accepted as legacy input.)        │
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
│   Timestamp normalization  →  Butterworth LP filter (5 Hz, order 4) │
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
│   MetadataLoader  ─── load_skier_profile("skier_01")                │
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

## Related docs (canonical homes)

- **Master plan / roadmap / security / research protocol**: [`docs/MASTER_PLAN.md`](MASTER_PLAN.md)
- **Algorithm assumptions + thresholds**: [`docs/algorithm-spec.md`](algorithm-spec.md)
- **Upload ZIP + CSV formats**: [`docs/data.md`](data.md)
