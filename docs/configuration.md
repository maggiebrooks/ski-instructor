# Configuration & Output

## Canonical references

- **Pipeline parameters + thresholds** live in [`docs/algorithm-spec.md`](algorithm-spec.md).
  This includes filter `cutoff/order`, segmentation thresholds, and turn-detection
  parameters with their validation status.
- This doc is intentionally limited to **output artifacts** (what files exist
  after a run) and the **summary schema**.

---

## Output Artifacts

| File | Format | Description |
|------|--------|-------------|
| `data/processed/<session>_processed.csv` | CSV | Full merged, filtered, segmented, feature-enriched dataset |
| `data/processed/<session>_summary.json` | JSON | Session + per-run metrics |
| `data/processed/all_sessions_overview.json` | JSON | Combined metrics for all sessions |
| `data/ski.db` | SQLite | Persistent queryable database (sessions, runs, turns tables) |
| `output/<session>_session.png` | PNG (150 dpi) | 5-panel session overview with activity shading + turn radius scatter |

---

## Summary JSON Schema

```json
{
  "session_duration_s": 3530.05,
  "total_samples": 70563,
  "sample_rate_hz": 20,
  "time_skiing_s": 1666.3,
  "time_lift_s": 1009.1,
  "time_idle_s": 854.6,
  "num_runs": 9,
  "total_turns": 556,
  "total_vertical_m": 1693.2,
  "avg_run_duration_s": 185.2,
  "avg_run_vertical_m": 188.1,
  "avg_turns_per_run": 61.8,
  "max_speed_kmh": 59.7,

  "avg_turn_angle_deg": 24.5,
  "avg_turn_radius_m": 8.5,
  "avg_speed_at_apex_kmh": 25.8,
  "avg_symmetry": 0.73,
  "total_turns_left": 291,
  "total_turns_right": 265,

  "runs": [
    {
      "run_id": 5,
      "start_s": 627.8,
      "end_s": 898.8,
      "duration_s": 271.0,
      "vertical_drop_m": 322.4,
      "num_turns": 60,
      "avg_speed_ms": 8.16,
      "max_speed_ms": 16.58,
      "max_speed_kmh": 59.7,
      "mean_accel_mag": 2.843,
      "max_accel_mag": 16.541,

      "avg_turn_angle_deg": 26.8,
      "avg_turn_radius_m": 10.7,
      "avg_edge_angle_deg": 55.3,
      "avg_speed_at_apex_kmh": 33.9,
      "avg_symmetry": 0.70,
      "turns_left": 32,
      "turns_right": 28,

      "per_turn": [
        {
          "turn_id": 1,
          "sensor_source": "pelvis_phone",
          "time_s": 704.6,
          "direction": "left",
          "duration_s": 1.0,
          "speed_at_apex_kmh": 27.6,
          "speed_loss_ratio": 0.0,

          "initiation_start_time": 704.31,
          "apex_time": 704.56,
          "finish_end_time": 704.66,

          "pelvis_turn_angle_deg": -14.6,
          "pelvis_peak_rotation_rate": 1.836,
          "pelvis_turn_radius_m": 4.2,
          "pelvis_max_roll_angle_deg": 43.4,
          "pelvis_peak_g_force": 0.74,
          "pelvis_symmetry": 1.0,
          "pelvis_edge_build_progressiveness": 89.0,
          "pelvis_radius_stability_cov": 1.05
        }
      ]
    }
  ]
}
```

---

## Database Schema (`data/ski.db`)

The pipeline writes to a SQLite database alongside the JSON output.
The processing/algorithm version is tracked via `PROCESSING_VERSION`
(currently `2.0.0`) and stored in the DB `schema_version` column.
These are conceptually separate and will be split when analytics versioning
diverges from the DB schema.

IMU-derived columns use a `pelvis_` prefix to clarify sensor origin.
When a second sensor (e.g. boot cuff IMU) is added, its columns will
use a `boot_` prefix, sharing the same row via `turn_id`.

```
sessions
├── session_id TEXT PRIMARY KEY    (folder name)
├── date TEXT                      (extracted YYYY-MM-DD)
├── duration_seconds REAL
├── total_vertical REAL
├── num_runs INTEGER
├── total_turns INTEGER
├── max_speed_kmh REAL
└── schema_version TEXT

runs
├── run_id TEXT PRIMARY KEY        (session_id + _run_ + index)
├── session_id TEXT → sessions
├── run_index INTEGER
├── duration_seconds REAL
├── vertical REAL
├── avg_speed REAL
├── max_speed_kmh REAL
├── num_turns INTEGER
├── turns_left INTEGER
└── turns_right INTEGER

turns
├── turn_id TEXT PRIMARY KEY       (run_id + _turn_ + index)
├── run_id TEXT → runs
├── turn_index INTEGER
├── sensor_source TEXT             (default: "pelvis_phone")
├── direction TEXT
├── duration_seconds REAL
├── speed_at_apex REAL             (km/h, GPS-derived)
├── speed_loss_ratio REAL          (GPS-derived)
├── pelvis_integrated_turn_angle REAL   (degrees)
├── pelvis_peak_angular_velocity REAL   (rad/s)
├── pelvis_max_roll_angle REAL          (degrees)
├── pelvis_estimated_turn_radius REAL   (meters)
├── pelvis_peak_g_force REAL
├── pelvis_symmetry REAL                (0-1)
├── pelvis_edge_build_progressiveness REAL (deg/s)
└── pelvis_radius_stability REAL        (CoV, lower = better)
```

Duplicate inserts are handled via `INSERT OR REPLACE`. The database
is additive -- JSON output is preserved alongside it.

---

## Upload preflight gates (before enqueue)

The API runs a cheap **preflight validation** step *before* enqueueing an RQ job.
This prevents wasting worker cycles on obviously junk uploads (too short / too long / too large).

Configure via env vars (see `backend/config.py` defaults):

- `PREFLIGHT_MIN_DURATION_S`
- `PREFLIGHT_MAX_DURATION_S`
- `PREFLIGHT_MIN_ROWS`
- `PREFLIGHT_MAX_ROWS`
- `PREFLIGHT_FLAG_MIN_DURATION_S` (accept-but-warn threshold)
- `PREFLIGHT_FLAG_MIN_ROWS` (accept-but-warn threshold)

### Raw retention cleanup (optional)

If you want a simple raw-data lifecycle policy (raw → processed → delete), run:

```bash
python scripts/cleanup_raw_sessions.py
```

Configure via env vars:

- `RAW_RETENTION_DAYS` (default `30`)
- `RAW_DELETE_REQUIRES_PROCESSED` (default `true`)

### Example Queries

```sql
-- All left turns faster than 40 km/h with tight radius
SELECT * FROM turns
WHERE direction = 'left'
  AND speed_at_apex > 40
  AND pelvis_estimated_turn_radius < 8;

-- Average radius stability by session
SELECT s.session_id, s.date, AVG(t.pelvis_radius_stability) as avg_cov
FROM turns t
JOIN runs r ON t.run_id = r.run_id
JOIN sessions s ON r.session_id = s.session_id
GROUP BY s.session_id;
```
