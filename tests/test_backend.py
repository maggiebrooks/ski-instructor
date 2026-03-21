"""Tests for the backend API and worker pipeline."""

import io
import json
import os
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sensor_csv(rows=200, rate_hz=100):
    """Generate minimal Sensor Logger CSV content (Accel or Gyro)."""
    import random
    lines = ["time,seconds_elapsed,z,y,x"]
    base = 1_700_000_000_000_000_000
    for i in range(rows):
        t = base + int(i * 1e9 / rate_hz)
        se = f"{i / rate_hz:.4f}"
        z = f"{random.uniform(-2, 2):.4f}"
        y = f"{random.uniform(-2, 2):.4f}"
        x = f"{random.uniform(-2, 2):.4f}"
        lines.append(f"{t},{se},{z},{y},{x}")
    return "\n".join(lines)


def _make_orientation_csv(rows=200, rate_hz=100):
    """Generate minimal Orientation CSV with roll, pitch, yaw."""
    import random
    lines = ["time,seconds_elapsed,roll,pitch,yaw"]
    base = 1_700_000_000_000_000_000
    for i in range(rows):
        t = base + int(i * 1e9 / rate_hz)
        se = f"{i / rate_hz:.4f}"
        roll = f"{random.uniform(-30, 30):.4f}"
        pitch = f"{random.uniform(-10, 10):.4f}"
        yaw = f"{random.uniform(0, 360):.4f}"
        lines.append(f"{t},{se},{roll},{pitch},{yaw}")
    return "\n".join(lines)


def _make_location_csv(rows=50, rate_hz=1):
    """Generate minimal Location CSV with altitude descent for run detection."""
    lines = [
        "time,seconds_elapsed,latitude,longitude,altitude,"
        "altitudeAboveMeanSeaLevel,speed,bearing,"
        "horizontalAccuracy,verticalAccuracy"
    ]
    base = 1_700_000_000_000_000_000
    alt = 3500.0
    for i in range(rows):
        t = base + int(i * 1e9 / rate_hz)
        se = f"{i / rate_hz:.4f}"
        alt -= 2.0
        speed = f"{8 + (i % 5):.1f}"
        lines.append(
            f"{t},{se},39.18,-106.81,{alt:.1f},{alt:.1f},"
            f"{speed},180.0,5.0,3.0"
        )
    return "\n".join(lines)


def _make_barometer_csv(rows=50, rate_hz=1):
    lines = ["time,seconds_elapsed,pressure,relativeAltitude"]
    base = 1_700_000_000_000_000_000
    for i in range(rows):
        t = base + int(i * 1e9 / rate_hz)
        se = f"{i / rate_hz:.4f}"
        lines.append(f"{t},{se},660.0,{-i * 2.0:.1f}")
    return "\n".join(lines)


def _make_gravity_csv(rows=200, rate_hz=100):
    lines = ["time,seconds_elapsed,z,y,x"]
    base = 1_700_000_000_000_000_000
    for i in range(rows):
        t = base + int(i * 1e9 / rate_hz)
        se = f"{i / rate_hz:.4f}"
        lines.append(f"{t},{se},-9.8,0.0,0.0")
    return "\n".join(lines)


def _make_session_zip() -> bytes:
    """Build a minimal valid Sensor Logger session ZIP in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Accelerometer.csv", _make_sensor_csv())
        zf.writestr("Gyroscope.csv", _make_sensor_csv())
        zf.writestr("Orientation.csv", _make_orientation_csv())
        zf.writestr("Location.csv", _make_location_csv())
        zf.writestr("Barometer.csv", _make_barometer_csv())
        zf.writestr("Gravity.csv", _make_gravity_csv())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Upload endpoint tests (mock Redis so no running server needed)
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    """Test POST /api/upload-session using FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def _patch_queue(self):
        mock_queue = MagicMock()
        with patch("backend.routes.upload._get_queue", return_value=mock_queue):
            self.mock_queue = mock_queue
            yield

    @pytest.fixture
    def client(self):
        from backend.app import app
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _clean_raw_dir(self):
        yield
        raw = Path("sessions/raw")
        if raw.exists():
            for child in raw.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)

    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["message"] == "ski-ai backend running"

    def test_upload_returns_session_id(self, client):
        data = _make_session_zip()
        resp = client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["status"] == "processing"

    def test_upload_extracts_zip(self, client):
        data = _make_session_zip()
        resp = client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        sid = resp.json()["session_id"]
        session_dir = Path("sessions/raw") / sid
        assert session_dir.exists()
        assert (session_dir / "Accelerometer.csv").exists()
        assert (session_dir / "Gyroscope.csv").exists()

    def test_upload_enqueues_job(self, client):
        data = _make_session_zip()
        client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        self.mock_queue.enqueue.assert_called_once()
        args = self.mock_queue.enqueue.call_args
        assert args[0][0] == "backend.worker.run_pipeline"

    def test_rejects_non_zip(self, client):
        resp = client.post(
            "/api/upload-session",
            files={"file": ("bad.txt", b"not a zip", "text/plain")},
        )
        assert resp.status_code == 400
        assert "not a valid ZIP" in resp.json()["detail"]

    def test_rejects_zip_without_imu(self, client):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("notes.txt", "nothing useful")
        resp = client.post(
            "/api/upload-session",
            files={"file": ("bad.zip", buf.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        assert "Accelerometer.csv" in resp.json()["detail"]

    def test_rejects_oversized_file(self, client):
        with patch("backend.routes.upload.MAX_UPLOAD_MB", 0):
            data = _make_session_zip()
            resp = client.post(
                "/api/upload-session",
                files={"file": ("session.zip", data, "application/zip")},
            )
            assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Worker / pipeline integration test (no Redis needed)
# ---------------------------------------------------------------------------

class TestWorkerPipeline:
    """Test run_pipeline() directly -- calls the real pipeline on synthetic data."""

    @staticmethod
    def _write_sensor_csvs(target_dir: Path):
        """Write synthetic Sensor Logger CSVs into *target_dir*."""
        import numpy as np
        import pandas as pd

        np.random.seed(42)
        n = 6000  # 60s @ 100 Hz
        base_ns = 1_700_000_000_000_000_000
        times = base_ns + np.arange(n) * 10_000_000

        def _write(name, cols):
            pd.DataFrame(cols).to_csv(str(target_dir / name), index=False)

        _write("Accelerometer.csv", {
            "time": times,
            "seconds_elapsed": np.arange(n) / 100,
            "x": np.random.normal(0, 0.5, n),
            "y": np.random.normal(0, 0.5, n),
            "z": np.random.normal(-9.8, 0.3, n),
        })

        gyro_z = 2.0 * np.sin(2 * np.pi * 0.15 * np.arange(n) / 100)
        _write("Gyroscope.csv", {
            "time": times,
            "seconds_elapsed": np.arange(n) / 100,
            "x": np.random.normal(0, 0.1, n),
            "y": np.random.normal(0, 0.1, n),
            "z": gyro_z,
        })

        _write("Orientation.csv", {
            "time": times,
            "seconds_elapsed": np.arange(n) / 100,
            "roll": 20 * np.sin(2 * np.pi * 0.15 * np.arange(n) / 100),
            "pitch": np.random.normal(0, 2, n),
            "yaw": np.linspace(0, 360, n),
        })

        _write("Gravity.csv", {
            "time": times,
            "seconds_elapsed": np.arange(n) / 100,
            "x": np.zeros(n),
            "y": np.zeros(n),
            "z": np.full(n, -9.81),
        })

        loc_n = 60
        loc_times = base_ns + np.arange(loc_n) * 1_000_000_000
        _write("Location.csv", {
            "time": loc_times,
            "seconds_elapsed": np.arange(loc_n).astype(float),
            "latitude": np.full(loc_n, 39.18),
            "longitude": np.full(loc_n, -106.81),
            "altitude": np.linspace(3500, 3400, loc_n),
            "altitudeAboveMeanSeaLevel": np.linspace(3500, 3400, loc_n),
            "speed": np.full(loc_n, 10.0),
            "bearing": np.full(loc_n, 180.0),
            "horizontalAccuracy": np.full(loc_n, 5.0),
            "verticalAccuracy": np.full(loc_n, 3.0),
        })

        _write("Barometer.csv", {
            "time": loc_times,
            "seconds_elapsed": np.arange(loc_n).astype(float),
            "pressure": np.full(loc_n, 660.0),
            "relativeAltitude": np.linspace(0, -100, loc_n),
        })

    def test_run_pipeline_produces_report(self, tmp_path):
        """Full integration: run_pipeline -> report.json."""
        from backend.worker import run_pipeline

        session_id = "test_integration_session"

        raw_parent = tmp_path / "raw"
        target = raw_parent / session_id
        target.mkdir(parents=True)
        self._write_sensor_csvs(target)

        proc_dir = tmp_path / "processed"
        plots_dir = tmp_path / "plots"
        db_path = str(tmp_path / "test.db")

        test_buckets = {
            "raw": raw_parent,
            "processed": proc_dir,
            "plots": plots_dir,
        }

        with (
            patch("backend.worker.RAW_DIR", raw_parent),
            patch("backend.storage.BUCKETS", test_buckets),
            patch("backend.worker.DB_PATH", db_path),
            patch("backend.validation.output_validator.DB_PATH", db_path),
            patch("backend.validation.output_validator.BUCKETS", test_buckets),
            patch("backend.worker.update_job"),
        ):
            report = run_pipeline(session_id)

        assert report["session_id"] == session_id
        assert report["status"] == "complete"
        assert report["processing_version"] == "2.0.0"
        assert "summary" in report
        assert "scores" in report
        assert "insights" in report

        report_file = proc_dir / session_id / "report.json"
        assert report_file.exists()
        with open(report_file) as f:
            saved = json.load(f)
        assert saved["session_id"] == session_id
        assert "confidence_threshold_used" in saved
        assert saved["confidence_threshold_used"] == 0.7
        assert "total_turn_count" in saved
        assert "filtered_turn_count" in saved
        assert "low_confidence_warning" in saved
        assert "score_confidence" in saved
        assert saved["score_confidence"] in ("low", "medium", "high")
        assert "warnings" in saved
        assert "top_insight" in saved
        assert saved["top_insight"] is None or isinstance(saved["top_insight"], str)

        from backend.worker import TOP_COACHING_INSIGHTS_N

        insights = saved["insights"]
        assert len(insights) <= TOP_COACHING_INSIGHTS_N + 1
        if insights:
            assert not any("[" in line and "]" in line for line in insights)


# ---------------------------------------------------------------------------
# Session retrieval endpoint tests
# ---------------------------------------------------------------------------

class TestSessionEndpoints:
    """Test GET /api/session/*, /api/sessions, and plot serving."""

    @pytest.fixture(autouse=True)
    def _patch_queue(self):
        mock_queue = MagicMock()
        with patch("backend.routes.upload._get_queue", return_value=mock_queue):
            yield

    @pytest.fixture
    def client(self):
        from backend.app import app
        return TestClient(app)

    def test_get_session_not_found(self, client):
        with patch("backend.routes.sessions.get_job", return_value=None):
            resp = client.get("/api/session/nonexistent")
        assert resp.status_code == 404

    def test_get_session_processing(self, client, tmp_path):
        job = {
            "job_id": "j1",
            "session_id": "sid1",
            "status": "processing",
            "progress_stage": "analyzing",
            "error_message": None,
        }
        with (
            patch("backend.routes.sessions.get_job", return_value=job),
            patch("backend.routes.sessions.PROCESSED_DIR", tmp_path),
        ):
            resp = client.get("/api/session/sid1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processing"
        assert body["progress"] == "analyzing"
        assert body["report"] is None

    def test_get_session_complete(self, client, tmp_path):
        job = {
            "job_id": "j2",
            "session_id": "sid2",
            "status": "complete",
            "progress_stage": "complete",
            "error_message": None,
        }
        report_dir = tmp_path / "sid2"
        report_dir.mkdir()
        report = {"session_id": "sid2", "status": "complete", "summary": {"runs": 5}}
        with open(report_dir / "report.json", "w") as f:
            json.dump(report, f)

        with (
            patch("backend.routes.sessions.get_job", return_value=job),
            patch("backend.routes.sessions.PROCESSED_DIR", tmp_path),
        ):
            resp = client.get("/api/session/sid2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "complete"
        assert body["report"]["summary"]["runs"] == 5

    def test_list_sessions_empty(self, client, tmp_path):
        with patch("backend.routes.sessions.PROCESSED_DIR", tmp_path):
            resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sessions_with_data(self, client, tmp_path):
        import os

        for sid in ["aaa", "bbb"]:
            d = tmp_path / sid
            d.mkdir()
            report = {"summary": {"runs": 3, "turns": 50}}
            with open(d / "report.json", "w") as f:
                json.dump(report, f)
        # bbb report newer → should sort first (newest first)
        os.utime(tmp_path / "aaa" / "report.json", (1_600_000_000, 1_600_000_000))
        os.utime(tmp_path / "bbb" / "report.json", (1_700_000_000, 1_700_000_000))

        with patch("backend.routes.sessions.PROCESSED_DIR", tmp_path):
            resp = client.get("/api/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        ids = {s["session_id"] for s in body}
        assert ids == {"aaa", "bbb"}
        assert body[0]["session_id"] == "bbb"
        assert body[0]["summary"]["runs"] == 3
        assert body[0]["status"] == "complete"
        assert "scores" in body[0]
        assert "top_insight" in body[0]
        assert "created_at" in body[0]

    def test_get_plot_not_found(self, client, tmp_path):
        with patch("backend.routes.sessions.PLOTS_DIR", tmp_path):
            resp = client.get("/api/session/sid1/plot/missing.png")
        assert resp.status_code == 404

    def test_get_plot_serves_image(self, client, tmp_path):
        plot_dir = tmp_path / "sid1"
        plot_dir.mkdir()
        png_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"
        with open(plot_dir / "turn_signature.png", "wb") as f:
            f.write(png_bytes)

        with patch("backend.routes.sessions.PLOTS_DIR", tmp_path):
            resp = client.get("/api/session/sid1/plot/turn_signature.png")
        assert resp.status_code == 200
        assert resp.content == png_bytes

    def test_plot_path_traversal_blocked(self, client, tmp_path):
        with patch("backend.routes.sessions.PLOTS_DIR", tmp_path):
            resp = client.get("/api/session/sid1/plot/..test.png")
        assert resp.status_code == 400
        assert "Invalid plot name" in resp.json()["detail"]

    def test_delete_session_not_found(self, client, tmp_path):
        raw = tmp_path / "raw"
        plots = tmp_path / "plots"
        processed = tmp_path / "processed"
        raw.mkdir()
        processed.mkdir()
        plots.mkdir()
        db_file = tmp_path / "ski.db"
        with (
            patch("backend.routes.sessions.PROCESSED_DIR", processed),
            patch("backend.routes.sessions.RAW_DIR", raw),
            patch("backend.routes.sessions.PLOTS_DIR", plots),
            patch("backend.routes.sessions.get_job", return_value=None),
            patch("backend.routes.sessions.DB_PATH", str(db_file)),
        ):
            resp = client.delete("/api/session/" + "0" * 32)
        assert resp.status_code == 404

    def test_delete_session_success(self, client, tmp_path):
        from data.database import init_db

        raw = tmp_path / "raw"
        plots = tmp_path / "plots"
        processed = tmp_path / "processed"
        sid = "a" * 32
        d = processed / sid
        d.mkdir(parents=True)
        with open(d / "report.json", "w") as f:
            json.dump({"session_id": sid}, f)

        db_file = tmp_path / "ski.db"
        conn = init_db(str(db_file))
        conn.close()

        with (
            patch("backend.routes.sessions.PROCESSED_DIR", processed),
            patch("backend.routes.sessions.RAW_DIR", raw),
            patch("backend.routes.sessions.PLOTS_DIR", plots),
            patch("backend.routes.sessions.get_job", return_value=None),
            patch("backend.routes.sessions.DB_PATH", str(db_file)),
            patch("backend.models.DB_PATH", str(db_file)),
        ):
            resp = client.delete(f"/api/session/{sid}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}
        assert not d.exists()


# ---------------------------------------------------------------------------
# Models (jobs table) unit tests
# ---------------------------------------------------------------------------

class TestJobsModels:
    """Test create_job / get_job / update_job directly."""

    def test_create_and_get(self, tmp_path):
        from backend.models import create_job, get_job

        db = str(tmp_path / "test.db")
        job_id = create_job("sess_1", db_path=db)
        assert isinstance(job_id, str)
        assert len(job_id) == 32

        job = get_job("sess_1", db_path=db)
        assert job is not None
        assert job["session_id"] == "sess_1"
        assert job["status"] == "processing"
        assert job["progress_stage"] == "processing"

    def test_get_missing_returns_none(self, tmp_path):
        from backend.models import get_job

        db = str(tmp_path / "test.db")
        assert get_job("nonexistent", db_path=db) is None

    def test_update_progress(self, tmp_path):
        from backend.models import create_job, get_job, update_job

        db = str(tmp_path / "test.db")
        create_job("sess_2", db_path=db)

        update_job("sess_2", "analyzing", db_path=db)
        job = get_job("sess_2", db_path=db)
        assert job["progress_stage"] == "analyzing"
        assert job["status"] == "processing"

    def test_update_complete(self, tmp_path):
        from backend.models import create_job, get_job, update_job

        db = str(tmp_path / "test.db")
        create_job("sess_3", db_path=db)

        update_job("sess_3", "complete", db_path=db)
        job = get_job("sess_3", db_path=db)
        assert job["status"] == "complete"
        assert job["progress_stage"] == "complete"

    def test_update_error(self, tmp_path):
        from backend.models import create_job, get_job, update_job

        db = str(tmp_path / "test.db")
        create_job("sess_4", db_path=db)

        update_job("sess_4", "error", error="Something broke", db_path=db)
        job = get_job("sess_4", db_path=db)
        assert job["status"] == "error"
        assert job["progress_stage"] == "error"
        assert job["error_message"] == "Something broke"

    def test_create_job_with_hash(self, tmp_path):
        from backend.models import create_job, get_job

        db = str(tmp_path / "test.db")
        job_id = create_job("sess_h1", session_hash="abc123hash", db_path=db)
        assert isinstance(job_id, str)

        job = get_job("sess_h1", db_path=db)
        assert job["session_hash"] == "abc123hash"

    def test_lookup_by_hash_found(self, tmp_path):
        from backend.models import create_job, lookup_by_hash

        db = str(tmp_path / "test.db")
        create_job("sess_lh", session_hash="deadbeef", db_path=db)

        found = lookup_by_hash("deadbeef", db_path=db)
        assert found == "sess_lh"

    def test_lookup_by_hash_not_found(self, tmp_path):
        from backend.models import lookup_by_hash

        db = str(tmp_path / "test.db")
        assert lookup_by_hash("nonexistent_hash", db_path=db) is None

    def test_lookup_by_hash_ignores_errored_jobs(self, tmp_path):
        from backend.models import create_job, update_job, lookup_by_hash

        db = str(tmp_path / "test.db")
        create_job("sess_err", session_hash="errhash", db_path=db)
        update_job("sess_err", "error", error="boom", db_path=db)

        assert lookup_by_hash("errhash", db_path=db) is None


# ---------------------------------------------------------------------------
# Duplicate upload detection tests
# ---------------------------------------------------------------------------

class TestDuplicateUpload:
    """Test SHA-256 dedup in POST /api/upload-session."""

    @pytest.fixture(autouse=True)
    def _patch_queue(self):
        mock_queue = MagicMock()
        with patch("backend.routes.upload._get_queue", return_value=mock_queue):
            self.mock_queue = mock_queue
            yield

    @pytest.fixture
    def client(self):
        from backend.app import app
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _clean_raw_dir(self):
        yield
        raw = Path("sessions/raw")
        if raw.exists():
            for child in raw.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)

    def test_duplicate_upload_returns_existing_session(self, client):
        data = _make_session_zip()
        resp1 = client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        assert resp1.status_code == 200
        sid1 = resp1.json()["session_id"]

        resp2 = client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["duplicate"] is True
        assert body2["session_id"] == sid1

    def test_duplicate_does_not_enqueue(self, client):
        data = _make_session_zip()
        client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        assert self.mock_queue.enqueue.call_count == 1

        client.post(
            "/api/upload-session",
            files={"file": ("session.zip", data, "application/zip")},
        )
        assert self.mock_queue.enqueue.call_count == 1  # still 1


# ---------------------------------------------------------------------------
# Metadata endpoint tests
# ---------------------------------------------------------------------------

class TestMetadataEndpoint:
    """Test GET /api/session/{session_id}/metadata."""

    @pytest.fixture(autouse=True)
    def _patch_queue(self):
        mock_queue = MagicMock()
        with patch("backend.routes.upload._get_queue", return_value=mock_queue):
            yield

    @pytest.fixture
    def client(self):
        from backend.app import app
        return TestClient(app)

    def test_metadata_empty_when_no_yaml(self, client, tmp_path):
        with (
            patch("backend.routes.metadata.RAW_DIR", tmp_path),
            patch("backend.routes.metadata.DATA_DIR", tmp_path / "data"),
        ):
            resp = client.get("/api/session/no_such_session/metadata")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_metadata_returns_session_and_profiles(self, client, tmp_path):
        import yaml

        session_dir = tmp_path / "raw" / "sess_meta"
        session_dir.mkdir(parents=True)
        session_meta = {"skier": "maggie", "ski": "test_ski", "resort": "Aspen"}
        with open(session_dir / "metadata.yaml", "w") as f:
            yaml.dump(session_meta, f)

        profiles_dir = tmp_path / "profiles"
        (profiles_dir / "skiers").mkdir(parents=True)
        (profiles_dir / "skis").mkdir(parents=True)
        with open(profiles_dir / "skiers" / "maggie.yaml", "w") as f:
            yaml.dump({"name": "Maggie", "level": "advanced"}, f)
        with open(profiles_dir / "skis" / "test_ski.yaml", "w") as f:
            yaml.dump({"model": "Sheeva 10", "length_cm": 158}, f)

        with (
            patch("backend.routes.metadata.RAW_DIR", tmp_path / "raw"),
            patch("backend.routes.metadata.DATA_DIR", tmp_path / "data"),
            patch("backend.routes.metadata.MetadataLoader",
                  return_value=MagicMock(
                      load_session_metadata=lambda p: session_meta if "sess_meta" in str(p) else None,
                      load_skier_profile=lambda sid: {"name": "Maggie", "level": "advanced"} if sid == "maggie" else None,
                      load_ski_profile=lambda sid: {"model": "Sheeva 10", "length_cm": 158} if sid == "test_ski" else None,
                  )),
        ):
            resp = client.get("/api/session/sess_meta/metadata")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session"]["resort"] == "Aspen"
        assert body["skier"]["name"] == "Maggie"
        assert body["ski"]["model"] == "Sheeva 10"


# ---------------------------------------------------------------------------
# Storage layer tests
# ---------------------------------------------------------------------------

class TestStorageLayer:
    """Test backend.storage get_path / write_bytes / read_path."""

    def test_get_path_creates_directory(self, tmp_path):
        from backend.storage import get_path

        buckets = {"plots": tmp_path / "plots"}
        with patch("backend.storage.BUCKETS", buckets):
            p = get_path("sess1", "plots", "chart.png")
        assert p == tmp_path / "plots" / "sess1" / "chart.png"
        assert p.parent.is_dir()

    def test_write_bytes_creates_file(self, tmp_path):
        from backend.storage import write_bytes

        buckets = {"processed": tmp_path / "processed"}
        with patch("backend.storage.BUCKETS", buckets):
            result = write_bytes("sess2", "processed", "report.json", b'{"ok":true}')
        assert result.exists()
        assert result.read_bytes() == b'{"ok":true}'

    def test_read_path_returns_correct_location(self, tmp_path):
        from backend.storage import read_path

        buckets = {"raw": tmp_path / "raw"}
        with patch("backend.storage.BUCKETS", buckets):
            p = read_path("sess3", "raw", "Accelerometer.csv")
        assert p == tmp_path / "raw" / "sess3" / "Accelerometer.csv"

    def test_invalid_bucket_raises(self):
        from backend.storage import get_path

        with pytest.raises(ValueError, match="Invalid storage bucket"):
            get_path("sess1", "nonexistent_bucket", "file.txt")

    def test_get_path_without_filename_returns_directory(self, tmp_path):
        from backend.storage import get_path

        buckets = {"processed": tmp_path / "processed"}
        with patch("backend.storage.BUCKETS", buckets):
            p = get_path("sess4", "processed")
        assert p == tmp_path / "processed" / "sess4"
        assert p.is_dir()
