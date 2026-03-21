# ski-ai: Project Vision

## 1. Purpose

ski-ai is a sensor-based ski analytics platform that transforms raw IMU and GPS data into actionable insights for skiers, coaches, and developers. Its primary goal is to bridge real-world ski movement with robust, scalable software systems, providing immediate feedback and enabling comparison across sessions.

**Key outcomes:**

- Per-session and per-turn metrics (speed, turn radius, edge angles, carving quality)
- Biomechanical insights via normalized, physics-informed scoring
- Modular, extensible platform for multi-sensor integration and advanced analytics
- Robust, reproducible system; **comparison and longitudinal analysis improve as more sessions are recorded** (deterministic pipeline; no ML retraining today)

## 2. Core Principles

- **Modularity:** Each stage of the pipeline is independent and pluggable.
- **Extensibility:** New sensors, analytics modules, or scoring algorithms can be added without rewriting the core.
- **Robustness:** Handles missing data, incomplete sessions, or optional metadata gracefully.
- **Comparison at scale:** More sessions enable better cross-session comparison and longitudinal views; future ML can build on the same deterministic metrics.
- **User-centered design:** End users can immediately consume results via JSON, CSV, SQLite queries, or visualizations.

## 3. High-Level Architecture

```
[Raw Sensor Data]              [Optional Metadata]
      │                                 │
      ▼                                 │
  Ingestion Layer                       │
      │                                 │
      ▼                                 │
  Preprocessing & Feature Modules       │
      │                                 │
      ▼                                 │
  Segmentation / Event Detection        │
      │                                 │
      ▼                                 │
  Persistence Layer (CSV / JSON / SQLite)
      │                                 │
      ▼                                 │
  Analytics Layer ◄────────────────────┘
  (metrics, scores, physics-based       metadata consumed here
   normalization: ski length today;     for normalized metrics
   height/weight planned)
      │
      ▼
  User-Facing Output
      ├─ JSON / CSV / SQLite queries
      ├─ PNG overview plots
      └─ Turn signatures / scoring feedback
```

**Notes:**

- Optional metadata is **consumed in the Analytics Layer** for physics-based normalization (e.g. ski-length normalized radius, future: weight-normalized g-force). It is not a separate “metadata normalization” stage at ingestion.
- Pipeline is deterministic but extensible for ML scoring later.
- Analytics and visualization modules are read-only; they consume DB/session outputs.

## 4. System Components

| Component | Description | Skills / Exposure |
|-----------|-------------|-------------------|
| Ingestion | Merge multi-sensor streams, align timestamps, generate derived features | ETL, time-series processing, pandas |
| Preprocessing | LP filtering, downsampling, compute magnitudes, orientation transformations | DSP, signal processing, physics-informed calculations |
| Segmentation | Identify skiing vs. lift vs. idle, per-run tracking | Event detection, thresholding, algorithmic design |
| Feature Modules | Turn detection, carving phase, radius & edge metrics | Modular plugin system, real-time feature extraction |
| Persistence | CSV/JSON export, SQLite database with versioned schema | Database design, query optimization, reproducibility |
| Analytics Layer | TurnAnalyzer + TurnInsights, physics-informed scoring, session comparison | Metric normalization, biomechanical interpretation, data modeling |
| Metadata System | YAML skier, ski, and session profiles | Configuration management, metadata-driven scoring, optional integration |
| Visualization | Session overview plots, turn signature curves, interactive potential | Data storytelling, UX for analytics, matplotlib |
| Testing & QA | 126+ unit tests across pipeline, analytics, and metadata | Test-driven development, synthetic data generation, edge-case validation |

## 5. Technical Highlights

- **Modular feature system:** New sensors or analytics modules can be plugged in with minimal changes to the core pipeline.
- **Metadata-aware normalization:** Scores normalized by **ski length today**; **skier height and weight** are in profiles and planned for future use (e.g. weight-normalized g-force).
- **Physics-informed scoring:** Turn radius, torso rotation ratio, and centripetal pressure ratio form the foundation for six movement scores.
- **Persistence & versioning:** Processed CSV, JSON, and SQLite DB with processing version tracking (2.0.0) ensure reproducibility.
- **Robustness:** Missing sensors, GPS dropouts, or absent metadata do not break the pipeline.
- **Test coverage:** 126 unit tests validate pipeline, analytics, scoring, and metadata handling.

## 6. Roadmap / Future Vision

See [README#Roadmap](../README.md#roadmap) and [architecture.md](architecture.md) for the full list. Highlights:

- Carving quality scoring (composite metric before ML)
- **Skier height/weight in normalization** (weight-normalized g-force, body-size adjustments)
- Dual-phone sensors: chest + boot cuff for upper/lower body separation
- Parameter tuning, notebooks, GPS track visualization, 3D slope replay
- Parquet output, hybrid segmentation, config file, advanced session comparison, ML turn quality scoring

## 7. Developer & User Benefits

- **Developers:** Exposure to real-time sensor ingestion, time-series processing, DSP, database design, modular architecture, testing, and physics-informed scoring.
- **Skiers/coaches:** Immediate insights into turn quality, speed, radius, and carving, with longitudinal tracking across sessions.
- **Researchers:** A clean, reproducible data pipeline for biomechanical analysis, ML modeling, or cross-session studies.

## 8. Why ski-ai is Unique

- Fully end-to-end sensor pipeline on iPhone sensor data
- Metadata-aware, physics-based normalization (ski length today; height/weight planned)
- Highly modular and test-driven, designed for future ML and dual-sensor integration
- Produces usable outputs out-of-the-box: CSV, JSON, SQLite, visualizations
- **Scales with data:** more sessions enable richer comparison and longitudinal analysis (and future ML can build on the same metrics)
