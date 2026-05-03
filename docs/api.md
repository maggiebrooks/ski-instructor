# API Reference

## HTTP Endpoints (FastAPI)

This doc is intentionally **endpoints only**.

For architecture and pipeline details, see:
- [`docs/architecture.md`](architecture.md)
- [`docs/MASTER_PLAN.md`](MASTER_PLAN.md)
- [`docs/configuration.md`](configuration.md) (env vars)

**Start the backend:**

```bash
redis-server                                                                  # Redis (required for job queue)
rq worker ski-pipeline --url "${REDIS_URL:-redis://localhost:6379}"          # Background worker (one process only)
uvicorn backend.app:app --reload --port 8000                                  # API server
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
| `file` | file | Session ZIP upload (see [`docs/data.md`](data.md)) |

**Validation:**
- Must be a valid ZIP archive (400 if not)
- Must contain `Accelerometer.csv` and `Gyroscope.csv` (400 if missing)
- Must not exceed `MAX_UPLOAD_MB` (413 if too large)
- May be rejected by **preflight gates** (400) before enqueue based on duration/row-count limits (see `PREFLIGHT_*` env vars).

**Duplicate detection:** The ZIP contents are SHA-256 hashed. If the same
data was uploaded before and the previous job is processing or complete, the
response returns the existing session instead of creating a new one.

**Success response (new upload):**

```json
{ "session_id": "a1b2c3...", "status": "processing" }
```

The response may also include optional fields when available:

- `preflight_status`: `"accept"` or `"flag"` (still accepted, but borderline)
- `warnings`: array of warning strings (upload accepted)
- `duration_s`: approximate duration in seconds
- `approx_hz`: approximate IMU sample rate

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
  "progress": "running_pipeline",
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

**Progress stages:** `queued` → `parsing_sensor_data` → `running_pipeline` → `generating_report` → `generating_plots` → `complete` (or `error`). Legacy values `processing` / `analyzing` may still appear on old jobs; treat them like `parsing_sensor_data` / `generating_report` in the UI.

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
