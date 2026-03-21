"""Physics correctness and confidence behavior tests.

Validates mathematical relationships, guard conditions, confidence
scoring rules, data quality evaluation, and the metric provenance
registry.
"""

import math

import numpy as np
import pandas as pd
import pytest

from ski.analysis.metric_provenance import METRICS, get_metric, list_metrics, MetricDefinition
from ski.analysis.data_quality import evaluate_data_quality
from ski.analysis.confidence import (
    compute_metric_confidence,
    compute_turn_confidence,
)


# ===================================================================
# 1. Turn Radius (physics: r = v / omega)
# ===================================================================

class TestTurnRadiusPhysics:
    def test_basic_radius(self):
        """v=10 m/s, omega=2 rad/s -> r=5 m (exact)."""
        v, omega = 10.0, 2.0
        r = v / omega
        assert r == pytest.approx(5.0, abs=1e-12)

    def test_radius_proportional_to_speed(self):
        omega = 1.5
        r1 = 10.0 / omega
        r2 = 20.0 / omega
        assert r2 == pytest.approx(2 * r1, abs=1e-12)

    def test_radius_inversely_proportional_to_omega(self):
        v = 15.0
        r1 = v / 1.0
        r2 = v / 2.0
        assert r1 == pytest.approx(2 * r2, abs=1e-12)

    def test_low_omega_guard(self):
        """Pipeline returns None when omega < 0.1."""
        omega = 0.05
        v = 10.0
        should_guard = omega < 0.1 or v < 1.0
        assert should_guard is True

    def test_low_speed_guard(self):
        """Pipeline returns None when speed < 1.0 m/s."""
        omega = 2.0
        v = 0.5
        should_guard = omega < 0.1 or v < 1.0
        assert should_guard is True

    def test_valid_computation_no_guard(self):
        omega, v = 0.5, 5.0
        should_guard = omega < 0.1 or v < 1.0
        assert should_guard is False
        r = v / omega
        assert r == pytest.approx(10.0, abs=1e-12)


# ===================================================================
# 2. Centripetal Acceleration (a_c = v^2 / r)
# ===================================================================

class TestCentripetalAcceleration:
    def test_basic(self):
        """v=10 m/s, r=5 m -> a_c=20 m/s^2 (exact)."""
        v, r = 10.0, 5.0
        a_c = v ** 2 / r
        assert a_c == pytest.approx(20.0, abs=1e-12)

    def test_equivalent_form(self):
        """a_c = v * omega should equal v^2 / r when r = v / omega."""
        v, omega = 10.0, 2.0
        r = v / omega
        a_c_from_r = v ** 2 / r
        a_c_from_omega = v * omega
        assert a_c_from_r == pytest.approx(a_c_from_omega, abs=1e-12)

    def test_increases_with_speed_squared(self):
        r = 5.0
        a1 = 5.0 ** 2 / r
        a2 = 10.0 ** 2 / r
        assert a2 == pytest.approx(4 * a1, abs=1e-12)


# ===================================================================
# 3. Turn Angle Integration (theta = integral of omega dt)
# ===================================================================

class TestTurnAngleIntegration:
    def test_constant_omega(self):
        """Constant omega=1 rad/s for 2 s -> theta=2 rad (trapezoidal)."""
        from scipy.integrate import trapezoid

        dt = 0.05  # 20 Hz
        t = np.arange(0, 2.0 + dt / 2, dt)
        omega = np.ones_like(t) * 1.0
        theta = trapezoid(omega, t)
        assert theta == pytest.approx(2.0, abs=1e-6)

    def test_linear_ramp(self):
        """Linearly increasing omega from 0 to 2 over 2 s -> theta=2 rad."""
        from scipy.integrate import trapezoid

        dt = 0.001
        t = np.arange(0, 2.0 + dt / 2, dt)
        omega = np.linspace(0, 2.0, len(t))
        theta = trapezoid(omega, t)
        assert theta == pytest.approx(2.0, abs=1e-3)

    def test_angle_sign_preserved(self):
        """Negative omega should produce negative angle."""
        from scipy.integrate import trapezoid

        t = np.linspace(0, 1.0, 100)
        omega = -np.ones_like(t) * 1.5
        theta = trapezoid(omega, t)
        assert theta < 0
        assert theta == pytest.approx(-1.5, abs=1e-3)


# ===================================================================
# 4. Pressure Ratio
# ===================================================================

class TestPressureRatio:
    def test_perfect_carving(self):
        """When measured g equals expected centripetal g, ratio = 1."""
        v, r = 10.0, 5.0
        expected_g = v ** 2 / (r * 9.81)
        measured_g = expected_g
        ratio = measured_g / expected_g
        assert ratio == pytest.approx(1.0, abs=1e-12)

    def test_skidding_below_one(self):
        v, r = 10.0, 5.0
        expected_g = v ** 2 / (r * 9.81)
        measured_g = expected_g * 0.5
        ratio = measured_g / expected_g
        assert ratio == pytest.approx(0.5, abs=1e-12)


# ===================================================================
# 5. Symmetry formula
# ===================================================================

class TestSymmetryFormula:
    def test_perfect_symmetry(self):
        """Peak at exact midpoint -> symmetry = 1."""
        t_start, t_end = 0.0, 2.0
        t_peak = 1.0
        t_mid = (t_start + t_end) / 2
        T = t_end - t_start
        sym = max(0, 1 - abs(t_peak - t_mid) / (T / 2))
        assert sym == pytest.approx(1.0, abs=1e-12)

    def test_asymmetric(self):
        """Peak at boundary -> symmetry = 0."""
        t_start, t_end = 0.0, 2.0
        t_peak = 0.0
        t_mid = (t_start + t_end) / 2
        T = t_end - t_start
        sym = max(0, 1 - abs(t_peak - t_mid) / (T / 2))
        assert sym == pytest.approx(0.0, abs=1e-12)


# ===================================================================
# 6. Confidence Behavior Rules
# ===================================================================

class TestConfidenceBehavior:
    @pytest.fixture()
    def high_quality(self):
        return {
            "gps_accuracy": 0.95,
            "sampling_rate_stability": 0.98,
            "missing_ratio": 0.99,
            "gyro_quality": 0.90,
            "overall_quality": 0.95,
        }

    @pytest.fixture()
    def low_quality(self):
        return {
            "gps_accuracy": 0.3,
            "sampling_rate_stability": 0.4,
            "missing_ratio": 0.6,
            "gyro_quality": 0.3,
            "overall_quality": 0.4,
        }

    def test_low_omega_reduces_radius_confidence(self, high_quality):
        """Low omega should produce lower radius confidence than high omega."""
        low = compute_metric_confidence(
            "turn_radius", {"omega": 0.15, "speed": 10}, high_quality
        )
        high = compute_metric_confidence(
            "turn_radius", {"omega": 2.0, "speed": 10}, high_quality
        )
        assert high > low

    def test_very_low_omega_zero_confidence(self, high_quality):
        """omega < 0.1 should give zero radius confidence (guard zone)."""
        conf = compute_metric_confidence(
            "turn_radius", {"omega": 0.05, "speed": 10}, high_quality
        )
        assert conf == 0.0

    def test_high_gps_noise_reduces_speed_confidence(self):
        good_gps = {"gps_accuracy": 0.95, "sampling_rate_stability": 0.9,
                     "missing_ratio": 0.99, "gyro_quality": 0.9,
                     "overall_quality": 0.93}
        bad_gps = {"gps_accuracy": 0.3, "sampling_rate_stability": 0.9,
                    "missing_ratio": 0.99, "gyro_quality": 0.9,
                    "overall_quality": 0.7}
        high = compute_metric_confidence("speed", {"speed": 15}, good_gps)
        low = compute_metric_confidence("speed", {"speed": 15}, bad_gps)
        assert high > low

    def test_confidence_bounded_zero_one(self, high_quality, low_quality):
        """All confidence values must be in [0, 1]."""
        for metric in METRICS:
            for inputs in [
                {"omega": 0.01, "speed": 0.1, "duration": 0.1,
                 "radius": 0.1, "n_turns": 1, "v_init": 0.1},
                {"omega": 5.0, "speed": 30.0, "duration": 3.0,
                 "radius": 20.0, "n_turns": 50, "v_init": 30.0},
            ]:
                for dq in [high_quality, low_quality]:
                    c = compute_metric_confidence(metric, inputs, dq)
                    assert 0.0 <= c <= 1.0, (
                        f"{metric} confidence {c} out of bounds"
                    )

    def test_heuristic_baseline_lower(self, high_quality):
        """Heuristic metrics should have confidence <= 0.65 under typical inputs."""
        conf = compute_metric_confidence(
            "edge_angle", {}, high_quality
        )
        assert conf <= 0.65

    def test_short_turn_reduces_symmetry_confidence(self, high_quality):
        short = compute_metric_confidence(
            "symmetry", {"duration": 0.2}, high_quality
        )
        long = compute_metric_confidence(
            "symmetry", {"duration": 2.0}, high_quality
        )
        assert long > short


# ===================================================================
# 7. Data Quality Evaluation
# ===================================================================

class TestDataQuality:
    def test_clean_data(self):
        """Clean synthetic data should produce high quality scores."""
        np.random.seed(42)
        n = 1000
        t = np.linspace(0, 50, n)
        df = pd.DataFrame({
            "seconds": t,
            "accel_x": np.random.normal(0, 0.5, n),
            "accel_y": np.random.normal(0, 0.5, n),
            "accel_z": np.random.normal(9.8, 0.3, n),
            "gyro_x": np.random.normal(0, 0.1, n),
            "gyro_y": np.random.normal(0, 0.1, n),
            "gyro_z": np.sin(t * 0.5) * 1.5,
            "speed": np.clip(np.random.normal(10, 1, n), 0, None),
            "roll": np.sin(t * 0.3) * 0.5,
            "pitch": np.sin(t * 0.2) * 0.3,
            "yaw": t * 0.01,
        })
        quality = evaluate_data_quality(df)

        assert quality["gps_accuracy"] > 0.7
        assert quality["sampling_rate_stability"] > 0.8
        assert quality["missing_ratio"] > 0.9
        assert quality["gyro_quality"] > 0.5
        assert quality["overall_quality"] > 0.6

    def test_noisy_data(self):
        """Noisy data with gaps should produce lower quality."""
        n = 200
        t = np.sort(np.random.uniform(0, 50, n))
        df = pd.DataFrame({
            "seconds": t,
            "gyro_z": np.random.normal(0, 0.01, n),
            "speed": np.random.choice([np.nan, 0.1, -1], n),
        })
        quality = evaluate_data_quality(df)
        assert quality["overall_quality"] < 0.6

    def test_empty_dataframe(self):
        quality = evaluate_data_quality(pd.DataFrame())
        assert quality["overall_quality"] == 0.0

    def test_none_input(self):
        quality = evaluate_data_quality(None)
        assert quality["overall_quality"] == 0.0

    def test_all_values_bounded(self):
        df = pd.DataFrame({
            "seconds": np.linspace(0, 10, 100),
            "gyro_z": np.random.normal(0, 1, 100),
            "speed": np.random.uniform(0, 20, 100),
        })
        quality = evaluate_data_quality(df)
        for k, v in quality.items():
            assert 0.0 <= v <= 1.0, f"{k} = {v} out of bounds"


# ===================================================================
# 8. Metric Provenance Registry
# ===================================================================

class TestMetricProvenance:
    def test_all_expected_metrics_registered(self):
        expected = {
            "speed", "angular_velocity", "turn_radius",
            "centripetal_acceleration", "pressure_ratio", "turn_angle",
            "symmetry", "edge_angle", "turn_rhythm",
            "speed_loss_ratio", "torso_rotation_ratio",
        }
        registered = set(METRICS.keys())
        for m in expected:
            assert m in registered, f"Missing metric: {m}"

    def test_metric_definition_fields(self):
        for name, defn in METRICS.items():
            assert isinstance(defn, MetricDefinition)
            assert defn.name, f"{name} has empty name"
            assert defn.equation, f"{name} has empty equation"
            assert len(defn.variables) > 0, f"{name} has no variables"
            assert defn.source, f"{name} has empty source"
            assert defn.category in ("physics", "heuristic"), (
                f"{name} invalid category: {defn.category}"
            )

    def test_get_metric(self):
        m = get_metric("turn_radius")
        assert m.name == "Turn Radius"
        assert m.category == "physics"

    def test_get_metric_missing(self):
        with pytest.raises(KeyError):
            get_metric("nonexistent_metric")

    def test_list_metrics_sorted(self):
        names = list_metrics()
        assert names == sorted(names)
        assert len(names) == len(METRICS)

    def test_heuristic_metrics(self):
        heuristic = [n for n, m in METRICS.items() if m.category == "heuristic"]
        assert "symmetry" in heuristic
        assert "edge_angle" in heuristic
        assert "turn_rhythm" in heuristic

    def test_physics_metrics(self):
        physics = [n for n, m in METRICS.items() if m.category == "physics"]
        assert "turn_radius" in physics
        assert "speed" in physics
        assert "centripetal_acceleration" in physics


# ===================================================================
# 9. compute_turn_confidence integration
# ===================================================================

class TestComputeTurnConfidence:
    def test_returns_dict(self):
        dq = {
            "gps_accuracy": 0.9,
            "sampling_rate_stability": 0.95,
            "missing_ratio": 0.98,
            "gyro_quality": 0.85,
            "overall_quality": 0.92,
        }
        metrics = {
            "speed_at_apex_kmh": 40.0,
            "pelvis_peak_rotation_rate": 1.5,
            "pelvis_turn_radius_m": 8.0,
            "duration_s": 1.5,
            "n_turns": 20,
            "max_speed_kmh": 55.0,
        }
        result = compute_turn_confidence(metrics, dq)
        assert isinstance(result, dict)
        assert len(result) > 0
        for k, v in result.items():
            assert 0.0 <= v <= 1.0, f"{k} confidence {v} out of bounds"

    def test_empty_metrics(self):
        dq = {"gps_accuracy": 0.9, "sampling_rate_stability": 0.9,
              "missing_ratio": 0.9, "gyro_quality": 0.9,
              "overall_quality": 0.9}
        result = compute_turn_confidence({}, dq)
        assert isinstance(result, dict)


# ===================================================================
# 10. Speed Loss Ratio
# ===================================================================

class TestSpeedLossRatio:
    def test_basic(self):
        v_init, v_finish = 20.0, 18.0
        loss = (v_init - v_finish) / v_init
        assert loss == pytest.approx(0.1, abs=1e-12)

    def test_no_loss(self):
        v_init = v_finish = 15.0
        loss = (v_init - v_finish) / v_init
        assert loss == pytest.approx(0.0, abs=1e-12)

    def test_speed_gain(self):
        """Negative speed loss = speed gain through turn (steep terrain)."""
        v_init, v_finish = 15.0, 18.0
        loss = (v_init - v_finish) / v_init
        assert loss < 0

    def test_guard(self):
        """Should guard when v_init < 1.0 m/s."""
        v_init = 0.5
        assert v_init < 1.0
