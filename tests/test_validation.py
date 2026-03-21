"""Tests for input and output validation."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.contracts.schemas import ValidationResult
from backend.validation.input_validator import validate_raw_session
from backend.validation.output_validator import validate_session_outputs
from backend.metrics.confidence import (
    compute_confidence,
    compute_data_quality_flags,
    LOW_GPS_CONFIDENCE,
    HIGH_SENSOR_NOISE,
    LOW_TURN_COUNT,
)
from backend.metrics.registry import METRIC_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_valid_session(tmp_path: Path, n_rows: int = 200) -> Path:
    """Write a minimal valid session to tmp_path."""
    base_ns = 1_700_000_000_000_000_000
    dt_ns = 10_000_000  # 100 Hz

    times = base_ns + np.arange(n_rows) * dt_ns
    accel = pd.DataFrame({
        "time": times,
        "x": np.random.uniform(-2, 2, n_rows),
        "y": np.random.uniform(-2, 2, n_rows),
        "z": np.random.uniform(8, 11, n_rows),
    })
    gyro = pd.DataFrame({
        "time": times,
        "x": np.random.uniform(-0.5, 0.5, n_rows),
        "y": np.random.uniform(-0.5, 0.5, n_rows),
        "z": np.random.uniform(-1.5, 1.5, n_rows),
    })

    accel.to_csv(tmp_path / "Accelerometer.csv", index=False)
    gyro.to_csv(tmp_path / "Gyroscope.csv", index=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_valid_session_passes(self, tmp_path):
        _write_valid_session(tmp_path)
        result = validate_raw_session(tmp_path)
        assert result.valid is True
        assert result.errors == []
        assert result.quality_score > 0

    def test_missing_accelerometer_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        (tmp_path / "Accelerometer.csv").unlink()
        with pytest.raises(ValueError, match="Missing required file"):
            validate_raw_session(tmp_path)

    def test_missing_gyroscope_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        (tmp_path / "Gyroscope.csv").unlink()
        with pytest.raises(ValueError, match="Missing required file"):
            validate_raw_session(tmp_path)

    def test_missing_columns_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Accelerometer.csv")
        df.drop(columns=["x"], inplace=True)
        df.to_csv(tmp_path / "Accelerometer.csv", index=False)
        with pytest.raises(ValueError, match="missing columns"):
            validate_raw_session(tmp_path)

    def test_empty_column_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Accelerometer.csv")
        df["x"] = np.nan
        df.to_csv(tmp_path / "Accelerometer.csv", index=False)
        with pytest.raises(ValueError, match="empty"):
            validate_raw_session(tmp_path)

    def test_nan_in_accel_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Accelerometer.csv")
        df.loc[0, "x"] = np.nan
        df.to_csv(tmp_path / "Accelerometer.csv", index=False)
        with pytest.raises(ValueError, match="NaN"):
            validate_raw_session(tmp_path)

    def test_extreme_accel_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Accelerometer.csv")
        df.loc[0, "x"] = 60.0
        df.to_csv(tmp_path / "Accelerometer.csv", index=False)
        with pytest.raises(ValueError, match="exceeds"):
            validate_raw_session(tmp_path)

    def test_extreme_gyro_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Gyroscope.csv")
        df.loc[0, "z"] = 60.0
        df.to_csv(tmp_path / "Gyroscope.csv", index=False)
        with pytest.raises(ValueError, match="exceeds"):
            validate_raw_session(tmp_path)

    def test_non_monotonic_timestamps_fails(self, tmp_path):
        _write_valid_session(tmp_path)
        df = pd.read_csv(tmp_path / "Accelerometer.csv")
        df.loc[0, "time"] = df.loc[1, "time"] + 1e9
        df.to_csv(tmp_path / "Accelerometer.csv", index=False)
        with pytest.raises(ValueError, match="monotonically"):
            validate_raw_session(tmp_path)

    def test_too_few_rows_fails(self, tmp_path):
        _write_valid_session(tmp_path, n_rows=5)
        with pytest.raises(ValueError, match="fewer than"):
            validate_raw_session(tmp_path)


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


class TestOutputValidation:
    def test_missing_session_dir_fails(self):
        with pytest.raises(ValueError, match="does not exist"):
            validate_session_outputs("nonexistent_session_999")

    def test_missing_report_fails(self, tmp_path, monkeypatch):
        session_dir = tmp_path / "test_session"
        session_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "backend.validation.output_validator.BUCKETS",
            {"processed": tmp_path, "raw": tmp_path, "plots": tmp_path},
        )
        with pytest.raises(ValueError, match="Missing report"):
            validate_session_outputs("test_session")


# ---------------------------------------------------------------------------
# Data quality flags
# ---------------------------------------------------------------------------


class TestDataQualityFlags:
    def test_low_gps_flag(self):
        flags = compute_data_quality_flags(
            {"gps_accuracy": 0.4, "gyro_quality": 0.9, "missing_ratio": 0.95},
        )
        assert LOW_GPS_CONFIDENCE in flags

    def test_high_sensor_noise_flag(self):
        flags = compute_data_quality_flags(
            {"gps_accuracy": 0.9, "gyro_quality": 0.3, "missing_ratio": 0.95},
        )
        assert HIGH_SENSOR_NOISE in flags

    def test_low_turn_count_flag(self):
        flags = compute_data_quality_flags(
            {"gps_accuracy": 0.9, "gyro_quality": 0.9},
            turn_count=3,
        )
        assert LOW_TURN_COUNT in flags

    def test_clean_data_no_flags(self):
        flags = compute_data_quality_flags(
            {"gps_accuracy": 0.95, "gyro_quality": 0.9, "missing_ratio": 0.98,
             "sampling_rate_stability": 0.95},
            turn_count=20,
            session_duration_s=600,
        )
        assert len(flags) == 0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestBackendConfidence:
    def test_compute_confidence_returns_dict(self):
        df = pd.DataFrame({
            "seconds": np.linspace(0, 10, 200),
            "gyro_z": np.sin(np.linspace(0, 2 * np.pi, 200)) * 1.5,
            "speed": np.random.uniform(5, 15, 200),
        })
        metadata = {
            "scores": {"pressure_ratio": 0.8, "torso_rotation_ratio": 0.3},
            "summary": {"total_turns": 20, "session_duration_s": 300},
        }
        result = compute_confidence(df, metadata)
        assert isinstance(result, dict)
        for k, v in result.items():
            assert 0 <= v <= 1

    def test_compute_confidence_empty_df(self):
        metadata = {"scores": {}, "summary": {"total_turns": 20}}
        result = compute_confidence(pd.DataFrame(), metadata)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------


class TestMetricRegistry:
    def test_all_expected_metrics_registered(self):
        expected = [
            "turn_radius", "pressure_ratio", "torso_rotation_ratio",
            "normalized_turn_radius", "rotary_stability", "edge_consistency",
            "pressure_management", "turn_symmetry", "turn_rhythm",
        ]
        for m in expected:
            assert m in METRIC_REGISTRY
            assert "units" in METRIC_REGISTRY[m]
            assert "equation" in METRIC_REGISTRY[m]
            assert "reference" in METRIC_REGISTRY[m]
            assert "assumptions" in METRIC_REGISTRY[m]
