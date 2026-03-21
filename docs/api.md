# API Reference

## HTTP Endpoints (FastAPI)

The backend runs on FastAPI with Redis Queue (RQ) for async processing.

**Start the backend:**

```bash
redis-server                                  # Redis (required for job queue)
rq worker ski-pipeline                         # Background worker
uvicorn backend.app:app --reload --port 8000   # API server
```

### Health Check

```
GET /api/health
```

Returns `{"message": "ski-ai backend running"}`.

---

### Upload Session

```
POST /api/upload-session
Content-Type: multipart/form-data
```

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Sensor Logger `.zip` export (max 200 MB) |

**Validation:**
- Must be a valid ZIP archive (400 if not)
- Must contain `Accelerometer.csv` and `Gyroscope.csv` (400 if missing)
- Must not exceed `MAX_UPLOAD_MB` (413 if too large)

**Duplicate detection:** The ZIP contents are SHA-256 hashed. If the same
data was uploaded before and the previous job is processing or complete, the
response returns the existing session instead of creating a new one.

**Success response (new upload):**

```json
{ "session_id": "a1b2c3...", "status": "processing" }
```

**Duplicate response:**

```json
{ "session_id": "a1b2c3...", "status": "complete", "duplicate": true }
```

---

### Get Session Status + Report

```
GET /api/session/{session_id}
```

Returns processing status and the full report when complete.

**During processing:**

```json
{
  "session_id": "a1b2c3...",
  "status": "processing",
  "progress": "analyzing",
  "report": null
}
```

**After completion:**

```json
{
  "session_id": "a1b2c3...",
  "status": "complete",
  "progress": "complete",
  "report": {
    "summary": { "runs": 8, "turns": 147, "vertical_m": 1200, ... },
    "scores": { "rotary_stability": 0.82, "edge_consistency": 0.71, ... },
    "normalized_metrics": { "pressure_ratio": 0.95, ... },
    "insights": ["Rotary Control: Very stable upper body...", ...]
  }
}
```

**On error:**

```json
{
  "session_id": "a1b2c3...",
  "status": "error",
  "progress": "error",
  "report": null
}
```

**404** if neither a job nor a report exists for the session.

**Progress stages:** `processing` -> `analyzing` -> `generating_plots` -> `complete` (or `error`).

---

### List Sessions

```
GET /api/sessions
```

Returns an array of all sessions that have a completed `report.json`.

```json
[
  { "session_id": "a1b2c3...", "summary": { "runs": 8, "turns": 147, ... } },
  { "session_id": "d4e5f6...", "summary": { "runs": 5, "turns": 92, ... } }
]
```

---

### Get Plot

```
GET /api/session/{session_id}/plot/{plot_name}
```

Serves a PNG plot for the session. Path traversal (`..`, `/`, `\`) is
rejected with 400.

Example:

```
GET /api/session/a1b2c3/plot/a1b2c3_turn_signature.png
```

---

### Get Metadata

```
GET /api/session/{session_id}/metadata
```

Returns session, skier, and ski metadata if `metadata.yaml` exists in the
session directory. Resolves linked skier and ski profiles from YAML.

```json
{
  "session": { "skier": "maggie", "ski": "sheeva10_104_158", "resort": "Aspen Highlands" },
  "skier": { "name": "Maggie", "level": "advanced" },
  "ski": { "model": "Sheeva 10", "length_cm": 158 }
}
```

Returns `{}` if no metadata exists.

---

## Configuration (`backend/config.py`)

All values can be overridden with environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_MODE` | `"local"` | `"local"` or `"s3"` (S3 not yet wired) |
| `RAW_DIR` | `sessions/raw` | Uploaded session files |
| `PROCESSED_DIR` | `sessions/processed` | Pipeline output (report.json, CSVs) |
| `PLOTS_DIR` | `sessions/plots` | Generated plot PNGs |
| `DATABASE_URL` | `sqlite:///data/ski.db` | SQLite database |
| `REDIS_URL` | `redis://localhost:6379` | Redis for RQ job queue |
| `MAX_UPLOAD_MB` | `200` | Maximum upload file size |

---

## Storage Layer (`backend/storage.py`)

Abstraction over local filesystem. All artifact writes go through this
module so the internals can later be swapped for S3/boto3 without changing
callers.

```python
from backend.storage import get_path, write_bytes, read_path

get_path("session_id", "plots")                     # -> Path to session dir
get_path("session_id", "plots", "signature.png")    # -> Path to specific file
write_bytes("session_id", "processed", "report.json", data)  # Write bytes
read_path("session_id", "raw", "Accelerometer.csv") # Get path for reading
```

Raises `ValueError` on invalid bucket names (`raw`, `processed`, `plots`
are the valid buckets).

---

## Job Tracking (`backend/models.py`)

SQLite `jobs` table tracks upload-to-completion lifecycle.

```python
from backend.models import create_job, get_job, update_job, lookup_by_hash

job_id = create_job("session_id", session_hash="sha256...")
job = get_job("session_id")          # Most recent job for this session
update_job("session_id", "analyzing")
update_job("session_id", "error", error="Pipeline crashed")
existing = lookup_by_hash("sha256...")  # Returns session_id or None
```

---

## Pipeline Orchestration (`ski/processing/session_processor.py`)

The `SessionProcessor` class runs the full analytics pipeline.

```python
from ski.processing.session_processor import SessionProcessor

processor = SessionProcessor(db_path="data/ski.db", processing_version="2.0.0")
summary = processor.process(
    session_id="my_session",
    raw_path=Path("data/MySession"),
    processed_dir=Path("sessions/processed/my_session"),
    output_dir=Path("sessions/plots/my_session"),
)
```

**Pipeline stages:** Ingestion -> Preprocessing -> Row features ->
Segmentation -> Turn detection -> Feature modules -> Session summary ->
Artifact writing -> Visualization -> SQLite persistence.

---

## Analytics Layer (`ski/analysis/`)

### TurnAnalyzer

Read-only queries against the SQLite turns table.

```python
analyzer = TurnAnalyzer("data/ski.db")
df = analyzer.load_turns(["session_id"])
metrics = analyzer.session_metrics("session_id")
comparison = analyzer.compare_sessions(["sess1", "sess2"])
```

### TurnInsights

Biomechanical interpretation with physics-based normalization.

```python
insights = TurnInsights()
scores = TurnInsights.compute_movement_scores(df, metadata)
fundamentals = TurnInsights.interpret_fundamentals(scores, metadata)
report = insights.session_report(analyzer, "session_id", metadata)
```

**Six movement scores (0-1):** rotary_stability, edge_consistency,
pressure_management, turn_symmetry, turn_shape_consistency, turn_rhythm.

**Three normalized metrics:** pressure_ratio, torso_rotation_ratio,
normalized_turn_radius.

### Turn Signature

```python
from ski.analysis.turn_signature import plot_session_signature
fig = plot_session_signature(analyzer, "session_id", show=False)
```

---

## Metadata (`ski/metadata/metadata_loader.py`)

```python
loader = MetadataLoader()
skier = loader.load_skier_profile("maggie")
ski = loader.load_ski_profile("sheeva10_104_158")
session_meta = loader.load_session_metadata(Path("data/MySession"))
```

Profiles are YAML files in `ski/profiles/skiers/` and `ski/profiles/skis/`.
Per-session metadata lives in `metadata.yaml` inside each session directory.
