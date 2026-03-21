"""Unit tests for the ski sensor pipeline.

Run with:  python -m pytest tests/ -v
"""
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

# Ensure transformations package is importable
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transformations.process_session import (
    load_sensor_file,
    compute_row_features,
    compute_turn_metrics,
    compute_pelvis_turn_metrics,
    detect_turn_phases,
    compute_carving_metrics,
    preprocess,
    detect_turns,
    segment_runs,
    compute_session_summary,
    detect_turns_by_run,
    discover_sessions,
)


# ---------------------------------------------------------------------------
# Helpers to build synthetic DataFrames
# ---------------------------------------------------------------------------

def _make_imu_df(n=1000, hz=100):
    """Minimal DataFrame that mimics post-ingestion, pre-preprocessing data."""
    t0 = 1_771_779_780_000_000_000
    step_ns = int(1e9 / hz)
    times = np.arange(t0, t0 + n * step_ns, step_ns, dtype=np.int64)[:n]

    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "time": times,
        "accel_x": rng.normal(0, 0.5, n),
        "accel_y": rng.normal(0, 0.5, n),
        "accel_z": rng.normal(0, 0.5, n),
        "gyro_x": rng.normal(0, 0.3, n),
        "gyro_y": rng.normal(0, 0.3, n),
        "gyro_z": rng.normal(0, 0.3, n),
    })


def _make_preprocessed_df(n=600, hz=20):
    """DataFrame that looks like output of preprocess() + compute_row_features()."""
    t0 = 1_771_779_780_000_000_000
    step_ns = int(1e9 / hz)
    times = np.arange(t0, t0 + n * step_ns, step_ns, dtype=np.int64)[:n]
    seconds = (times - times[0]) / 1e9

    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "time": times,
        "seconds": seconds,
        "timestamp": pd.to_datetime(times, unit="ns"),
        "accel_x": rng.normal(0, 0.5, n),
        "accel_y": rng.normal(0, 0.5, n),
        "accel_z": rng.normal(0, 0.5, n),
        "gyro_x": rng.normal(0, 0.3, n),
        "gyro_y": rng.normal(0, 0.3, n),
        "gyro_z": rng.normal(0, 0.3, n),
        "relativeAltitude": np.zeros(n),
        "altitudeAboveMeanSeaLevel": np.full(n, 3000.0),
        "speed": np.full(n, 5.0),
    })
    df = compute_row_features(df)
    return df


# ---------------------------------------------------------------------------
# load_sensor_file
# ---------------------------------------------------------------------------

class TestLoadSensorFile:
    def test_renames_xyz_with_prefix(self, tmp_path):
        csv = tmp_path / "sensor.csv"
        csv.write_text("time,seconds_elapsed,x,y,z\n1,0.0,1.0,2.0,3.0\n")

        df = load_sensor_file(str(csv), prefix="accel")
        assert "accel_x" in df.columns
        assert "accel_y" in df.columns
        assert "accel_z" in df.columns
        assert "x" not in df.columns
        assert "seconds_elapsed" not in df.columns

    def test_no_rename_without_prefix(self, tmp_path):
        csv = tmp_path / "sensor.csv"
        csv.write_text("time,seconds_elapsed,x,y,z\n1,0.0,1.0,2.0,3.0\n")

        df = load_sensor_file(str(csv))
        assert "x" in df.columns
        assert "seconds_elapsed" not in df.columns

    def test_non_xyz_columns_kept(self, tmp_path):
        csv = tmp_path / "loc.csv"
        csv.write_text("time,seconds_elapsed,latitude,longitude\n1,0.0,39.1,-106.9\n")

        df = load_sensor_file(str(csv))
        assert "latitude" in df.columns
        assert "seconds_elapsed" not in df.columns


# ---------------------------------------------------------------------------
# compute_row_features
# ---------------------------------------------------------------------------

class TestComputeRowFeatures:
    def test_magnitudes_correct(self):
        df = pd.DataFrame({
            "accel_x": [3.0], "accel_y": [4.0], "accel_z": [0.0],
            "gyro_x": [0.0], "gyro_y": [0.0], "gyro_z": [1.0],
        })
        result = compute_row_features(df)

        assert np.isclose(result["accel_mag"].iloc[0], 5.0)
        assert np.isclose(result["gyro_mag"].iloc[0], 1.0)

    def test_does_not_mutate_input(self):
        df = pd.DataFrame({
            "accel_x": [1.0], "accel_y": [0.0], "accel_z": [0.0],
            "gyro_x": [0.0], "gyro_y": [0.0], "gyro_z": [0.0],
        })
        original_cols = set(df.columns)
        _ = compute_row_features(df)
        assert set(df.columns) == original_cols

    def test_zero_values(self):
        df = pd.DataFrame({
            "accel_x": [0.0], "accel_y": [0.0], "accel_z": [0.0],
            "gyro_x": [0.0], "gyro_y": [0.0], "gyro_z": [0.0],
        })
        result = compute_row_features(df)
        assert result["accel_mag"].iloc[0] == 0.0
        assert result["gyro_mag"].iloc[0] == 0.0


# ---------------------------------------------------------------------------
# preprocess
# ---------------------------------------------------------------------------

class TestPreprocess:
    def test_downsamples_correctly(self):
        df = _make_imu_df(n=1000, hz=100)
        result = preprocess(df, source_hz=100, target_hz=20)
        assert len(result) == 200

    def test_adds_timestamp_and_seconds(self):
        df = _make_imu_df(n=500, hz=100)
        result = preprocess(df, source_hz=100, target_hz=50)
        assert "timestamp" in result.columns
        assert "seconds" in result.columns
        assert result["seconds"].iloc[0] == 0.0
        assert result["seconds"].iloc[-1] > 0

    def test_filter_reduces_high_freq_noise(self):
        n = 2000
        t0 = 1_771_779_780_000_000_000
        step_ns = 10_000_000  # 100 Hz
        times = np.arange(t0, t0 + n * step_ns, step_ns)[:n]
        t_sec = np.arange(n) / 100.0

        # Low-freq signal (1 Hz) + high-freq noise (40 Hz)
        signal = np.sin(2 * np.pi * 1.0 * t_sec) + 0.5 * np.sin(2 * np.pi * 40 * t_sec)

        df = pd.DataFrame({
            "time": times,
            "accel_x": signal,
            "accel_y": np.zeros(n),
            "accel_z": np.zeros(n),
            "gyro_x": np.zeros(n),
            "gyro_y": np.zeros(n),
            "gyro_z": np.zeros(n),
        })
        result = preprocess(df, source_hz=100, cutoff=5.0, target_hz=100)

        # High-freq noise should be largely removed
        residual_power = np.var(result["accel_x"].values - np.sin(2 * np.pi * 1.0 * result["seconds"].values))
        assert residual_power < 0.01, f"Filter did not remove noise: var={residual_power:.4f}"


# ---------------------------------------------------------------------------
# detect_turns
# ---------------------------------------------------------------------------

class TestDetectTurns:
    def test_finds_known_peaks(self):
        n = 400
        gyro_z = np.zeros(n)
        peak_locations = [50, 150, 250, 350]
        for p in peak_locations:
            gyro_z[p] = 2.0  # clear peak

        df = pd.DataFrame({
            "gyro_z": gyro_z,
            "seconds": np.arange(n) / 20.0,
        })
        peaks, segments = detect_turns(df, height=0.5, distance=20)

        assert len(peaks) == 4
        np.testing.assert_array_equal(peaks, peak_locations)
        assert len(segments) == 4  # 4 peaks → boundary at start, 3 midpoints, end = 4 segments

    def test_negative_peaks_detected(self):
        n = 200
        gyro_z = np.zeros(n)
        gyro_z[60] = -1.5
        gyro_z[140] = -1.5

        df = pd.DataFrame({"gyro_z": gyro_z, "seconds": np.arange(n) / 20.0})
        peaks, _ = detect_turns(df, height=0.5, distance=20)
        assert len(peaks) == 2

    def test_no_peaks_in_flat_signal(self):
        df = pd.DataFrame({
            "gyro_z": np.zeros(200),
            "seconds": np.arange(200) / 20.0,
        })
        peaks, segments = detect_turns(df, height=0.5, distance=20)
        assert len(peaks) == 0

    def test_distance_parameter_respected(self):
        n = 200
        gyro_z = np.zeros(n)
        gyro_z[50] = 2.0
        gyro_z[55] = 2.0  # too close if distance=20

        df = pd.DataFrame({"gyro_z": gyro_z, "seconds": np.arange(n) / 20.0})
        peaks, _ = detect_turns(df, height=0.5, distance=20)
        assert len(peaks) == 1


# ---------------------------------------------------------------------------
# segment_runs
# ---------------------------------------------------------------------------

class TestSegmentRuns:
    def _make_altitude_profile(self, n=2400, hz=20):
        """Create a session with: idle, descent, idle, ascent, descent, idle."""
        t0 = 1_771_779_780_000_000_000
        step_ns = int(1e9 / hz)
        times = np.arange(t0, t0 + n * step_ns, step_ns)[:n]
        seconds = np.arange(n) / hz

        altitude = np.zeros(n)
        # 0-10s: idle (flat at 3000m)
        altitude[:200] = 3000.0
        # 10-30s: descent (-2 m/s → drops 40m)
        altitude[200:600] = np.linspace(3000, 2960, 400)
        # 30-40s: idle (flat at 2960)
        altitude[600:800] = 2960.0
        # 40-70s: ascent (+1 m/s → rises 30m)
        altitude[800:1400] = np.linspace(2960, 2990, 600)
        # 70-100s: descent (-1.5 m/s → drops 45m)
        altitude[1400:2000] = np.linspace(2990, 2945, 600)
        # 100-120s: idle
        altitude[2000:] = 2945.0

        rng = np.random.default_rng(99)
        df = pd.DataFrame({
            "time": times,
            "seconds": seconds,
            "timestamp": pd.to_datetime(times, unit="ns"),
            "accel_x": rng.normal(0, 0.2, n),
            "accel_y": rng.normal(0, 0.2, n),
            "accel_z": rng.normal(0, 0.2, n),
            "gyro_x": rng.normal(0, 0.1, n),
            "gyro_y": rng.normal(0, 0.1, n),
            "gyro_z": rng.normal(0, 0.1, n),
            "relativeAltitude": altitude - altitude[0],
            "altitudeAboveMeanSeaLevel": altitude,
            "speed": np.full(n, 5.0),
        })
        df = compute_row_features(df)
        return df

    def test_labels_added(self):
        df = self._make_altitude_profile()
        result = segment_runs(df, window_s=5, min_segment_s=3)
        assert "activity" in result.columns
        assert "run_id" in result.columns
        assert "alt_rate" in result.columns

    def test_detects_descents_as_skiing(self):
        df = self._make_altitude_profile()
        result = segment_runs(df, window_s=5, min_segment_s=3)
        activities = set(result["activity"].unique())
        assert "skiing" in activities

    def test_detects_ascent_as_lift(self):
        df = self._make_altitude_profile()
        result = segment_runs(df, window_s=5, min_segment_s=3)
        assert "lift" in set(result["activity"].unique())

    def test_run_ids_increment(self):
        df = self._make_altitude_profile()
        result = segment_runs(df, window_s=5, min_segment_s=3)
        ski_ids = sorted(result.loc[result["run_id"] > 0, "run_id"].unique())
        assert len(ski_ids) >= 2
        assert ski_ids == list(range(1, len(ski_ids) + 1))

    def test_does_not_mutate_input(self):
        df = self._make_altitude_profile()
        orig_cols = set(df.columns)
        _ = segment_runs(df, window_s=5, min_segment_s=3)
        assert set(df.columns) == orig_cols


# ---------------------------------------------------------------------------
# compute_session_summary
# ---------------------------------------------------------------------------

class TestComputeSessionSummary:
    def test_summary_structure(self):
        df = _make_preprocessed_df(n=600, hz=20)
        df["activity"] = "skiing"
        df["run_id"] = 1
        df["turn_peak"] = False

        run_results = [{
            "run_id": 1, "start_s": 0, "end_s": 30, "duration_s": 30,
            "vertical_drop_m": 50, "num_turns": 5, "avg_speed_ms": 8,
            "max_speed_ms": 15, "max_speed_kmh": 54, "mean_accel_mag": 1.5,
            "max_accel_mag": 8.0,
        }]

        summary = compute_session_summary(df, run_results)

        assert "session_duration_s" in summary
        assert "num_runs" in summary
        assert "total_turns" in summary
        assert "total_vertical_m" in summary
        assert "runs" in summary
        assert summary["num_runs"] == 1
        assert summary["total_turns"] == 5
        assert summary["total_vertical_m"] == 50

    def test_saves_json(self, tmp_path):
        df = _make_preprocessed_df(n=200, hz=20)
        df["activity"] = "idle"
        df["run_id"] = 0

        out = str(tmp_path / "summary.json")
        compute_session_summary(df, [], output_path=out)
        assert os.path.exists(out)

        import json
        with open(out) as f:
            data = json.load(f)
        assert "session_duration_s" in data


# ---------------------------------------------------------------------------
# discover_sessions
# ---------------------------------------------------------------------------

class TestDiscoverSessions:
    def test_finds_valid_sessions(self, tmp_path):
        s1 = tmp_path / "Session_A"
        s1.mkdir()
        (s1 / "Accelerometer.csv").write_text("time,x,y,z\n")
        (s1 / "Gyroscope.csv").write_text("time,x,y,z\n")

        s2 = tmp_path / "Session_B"
        s2.mkdir()
        (s2 / "Accelerometer.csv").write_text("time,x,y,z\n")
        # Missing Gyroscope.csv — should not be discovered

        sessions = discover_sessions(str(tmp_path))
        assert len(sessions) == 1
        assert "Session_A" in sessions[0]

    def test_returns_empty_for_no_sessions(self, tmp_path):
        sessions = discover_sessions(str(tmp_path))
        assert sessions == []


# ---------------------------------------------------------------------------
# compute_turn_metrics
# ---------------------------------------------------------------------------

class TestComputeTurnMetrics:

    @staticmethod
    def _make_turn_segment(n=40, hz=20, peak_pos=20, gyro_peak=1.5,
                           speed=10.0, roll_center=0.5, roll_amp=0.3):
        """Synthetic turn segment with a known gyro_z pulse."""
        seconds = np.arange(n) / hz
        gyro_z = np.zeros(n)
        # Gaussian-ish pulse centred at peak_pos
        for i in range(n):
            gyro_z[i] = gyro_peak * np.exp(-0.5 * ((i - peak_pos) / 4) ** 2)

        roll = roll_center + roll_amp * np.sin(np.linspace(0, np.pi, n))

        return pd.DataFrame({
            "seconds": seconds,
            "gyro_z": gyro_z,
            "speed": np.full(n, speed),
            "roll": roll,
            "accel_mag": np.full(n, 4.9),
        })

    def test_basic_metrics(self):
        seg = self._make_turn_segment()
        m = compute_turn_metrics(seg, peak_pos=20)

        assert m["sensor_source"] == "pelvis_phone"
        assert m["direction"] == "right"  # positive gyro_z pulse
        assert m["pelvis_turn_angle_deg"] > 0
        assert m["pelvis_peak_rotation_rate"] == pytest.approx(1.5, abs=0.01)
        assert m["speed_at_apex_kmh"] == pytest.approx(36.0, abs=0.1)
        assert m["duration_s"] > 0
        assert m["pelvis_peak_g_force"] == pytest.approx(4.9 / 9.807, abs=0.01)

    def test_left_turn(self):
        seg = self._make_turn_segment(gyro_peak=-2.0)
        m = compute_turn_metrics(seg, peak_pos=20)

        assert m["direction"] == "left"
        assert m["pelvis_turn_angle_deg"] < 0

    def test_turn_radius_computed(self):
        seg = self._make_turn_segment(speed=10.0, gyro_peak=1.0)
        m = compute_turn_metrics(seg, peak_pos=20)

        assert m["pelvis_turn_radius_m"] is not None
        assert m["pelvis_turn_radius_m"] == pytest.approx(10.0, abs=0.1)

    def test_radius_none_when_speed_too_low(self):
        seg = self._make_turn_segment(speed=0.5)
        m = compute_turn_metrics(seg, peak_pos=20)
        assert m["pelvis_turn_radius_m"] is None

    def test_radius_none_when_rotation_too_low(self):
        seg = self._make_turn_segment(gyro_peak=0.05)
        m = compute_turn_metrics(seg, peak_pos=20)
        assert m["pelvis_turn_radius_m"] is None

    def test_symmetry_perfect_when_peak_centered(self):
        n = 41
        seg = self._make_turn_segment(n=n, peak_pos=20)
        m = compute_turn_metrics(seg, peak_pos=20)
        assert m["pelvis_symmetry"] == pytest.approx(1.0, abs=0.05)

    def test_symmetry_lower_when_peak_offset(self):
        seg = self._make_turn_segment(n=40, peak_pos=5)
        m = compute_turn_metrics(seg, peak_pos=5)
        assert m["pelvis_symmetry"] < 0.7

    def test_edge_angle_range(self):
        seg = self._make_turn_segment(roll_center=0.5, roll_amp=0.3)
        m = compute_turn_metrics(seg, peak_pos=20)
        # sin(0..pi) peaks at 1.0, so range = roll_amp * 1 = 0.3 rad ≈ 17.2 deg
        assert m["pelvis_max_roll_angle_deg"] == pytest.approx(17.2, abs=1.0)

    def test_wrapper_matches_direct_call(self):
        seg = self._make_turn_segment()
        direct = compute_turn_metrics(seg, peak_pos=20)
        wrapped = compute_pelvis_turn_metrics(seg, peak_pos=20)
        assert direct == wrapped

    def test_does_not_mutate_input(self):
        seg = self._make_turn_segment()
        orig_vals = seg["gyro_z"].values.copy()
        _ = compute_turn_metrics(seg, peak_pos=20)
        np.testing.assert_array_equal(seg["gyro_z"].values, orig_vals)


# ---------------------------------------------------------------------------
# detect_turn_phases
# ---------------------------------------------------------------------------

class TestDetectTurnPhases:

    def test_finds_zero_crossings(self):
        # Signal: positive -> peak negative -> positive
        gz = np.array([0.3, 0.1, -0.5, -1.2, -0.8, -0.3, 0.2, 0.5])
        init, finish = detect_turn_phases(gz, peak_pos=3)
        # Crossing before peak: sign change between index 1 (+) and 2 (-)
        assert init == 2
        # Crossing after peak: sign change between index 5 (-) and 6 (+)
        assert finish == 5

    def test_no_crossing_before_peak_falls_back_to_zero(self):
        gz = np.array([-0.5, -1.0, -1.5, -0.8, -0.3, 0.2, 0.4])
        init, finish = detect_turn_phases(gz, peak_pos=2)
        assert init == 0
        assert finish == 4  # crossing between index 4 (-) and 5 (+)

    def test_no_crossing_after_peak_falls_back_to_end(self):
        gz = np.array([0.3, 0.1, -0.5, -1.2, -0.8, -0.4, -0.2])
        init, finish = detect_turn_phases(gz, peak_pos=3)
        assert init == 2
        assert finish == len(gz) - 1

    def test_short_segment_returns_boundaries(self):
        gz = np.array([1.0, -0.5])
        init, finish = detect_turn_phases(gz, peak_pos=0)
        assert init == 0
        assert finish == 1


# ---------------------------------------------------------------------------
# compute_carving_metrics
# ---------------------------------------------------------------------------

class TestComputeCarvingMetrics:

    @staticmethod
    def _make_carving_segment(n=40, hz=20, init_pos=10, apex_pos=20,
                              finish_pos=30, speed=10.0, gyro_peak=1.0):
        """Synthetic segment with linear roll ramp and constant gyro pulse."""
        seconds = np.arange(n) / hz
        gyro_z = np.zeros(n)
        for i in range(init_pos, finish_pos + 1):
            gyro_z[i] = gyro_peak * np.exp(-0.5 * ((i - apex_pos) / 5) ** 2)

        # Linear roll ramp from initiation to apex
        roll = np.zeros(n)
        if apex_pos > init_pos:
            roll[init_pos:apex_pos + 1] = np.linspace(0, 0.5, apex_pos - init_pos + 1)
        roll[apex_pos:finish_pos + 1] = np.linspace(0.5, 0, finish_pos - apex_pos + 1)

        return pd.DataFrame({
            "seconds": seconds,
            "gyro_z": gyro_z,
            "speed": np.full(n, speed),
            "roll": roll,
            "accel_mag": np.full(n, 4.9),
        })

    def test_basic_carving_metrics(self):
        seg = self._make_carving_segment()
        m = compute_carving_metrics(seg, init_pos=10, apex_pos=20, finish_pos=30)

        assert m["edge_build_progressiveness"] is not None
        assert m["edge_build_progressiveness"] > 0
        assert m["radius_stability_cov"] is not None
        assert m["radius_stability_cov"] >= 0
        # Constant speed -> speed loss should be ~0
        assert m["speed_loss_ratio"] is not None
        assert m["speed_loss_ratio"] == pytest.approx(0.0, abs=0.01)

    def test_zero_speed_guard(self):
        seg = self._make_carving_segment(speed=0.5)
        m = compute_carving_metrics(seg, init_pos=10, apex_pos=20, finish_pos=30)
        assert m["speed_loss_ratio"] is None

    def test_low_angular_velocity_guard(self):
        seg = self._make_carving_segment(gyro_peak=0.05)
        m = compute_carving_metrics(seg, init_pos=10, apex_pos=20, finish_pos=30)
        assert m["radius_stability_cov"] is None

    def test_constant_speed_through_turn(self):
        seg = self._make_carving_segment(speed=12.0)
        m = compute_carving_metrics(seg, init_pos=10, apex_pos=20, finish_pos=30)
        assert m["speed_loss_ratio"] == pytest.approx(0.0, abs=0.001)

    def test_does_not_mutate_input(self):
        seg = self._make_carving_segment()
        orig_gz = seg["gyro_z"].values.copy()
        orig_roll = seg["roll"].values.copy()
        _ = compute_carving_metrics(seg, init_pos=10, apex_pos=20, finish_pos=30)
        np.testing.assert_array_equal(seg["gyro_z"].values, orig_gz)
        np.testing.assert_array_equal(seg["roll"].values, orig_roll)
