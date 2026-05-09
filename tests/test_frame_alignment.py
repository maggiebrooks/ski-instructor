"""Tests for ski.frame_alignment static gravity alignment."""

import numpy as np
import pandas as pd

from ski.frame_alignment import align_session, build_rotation_matrix, estimate_gravity_vector


def test_identity_align_session_near_zero_magnitudes():
    """Phone already upright: gravity along sensor -z; after alignment, no residual."""
    n = 80
    df = pd.DataFrame(
        {
            "accel_x": np.zeros(n),
            "accel_y": np.zeros(n),
            "accel_z": np.full(n, -9.81),
            "gyro_x": np.zeros(n),
            "gyro_y": np.zeros(n),
            "gyro_z": np.zeros(n),
        }
    )
    df["accel_mag"] = np.sqrt(
        df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2
    )
    df["gyro_mag"] = np.zeros(n)

    out = align_session(df, sample_rate=20)
    np.testing.assert_allclose(out["accel_mag"].to_numpy(), 0.0, atol=0.1)
    np.testing.assert_allclose(out["gyro_mag"].to_numpy(), 0.0, atol=0.1)
    assert bool(out["frame_aligned"].all())


def test_ninety_degree_tilt_about_x_gravity_removed():
    """Gravity projects onto +y in sensor frame; after alignment, dynamic accel ~0."""
    n = 80
    df = pd.DataFrame(
        {
            "accel_x": np.zeros(n),
            "accel_y": np.full(n, 9.81),
            "accel_z": np.zeros(n),
            "gyro_x": np.zeros(n),
            "gyro_y": np.zeros(n),
            "gyro_z": np.zeros(n),
        }
    )
    df["accel_mag"] = np.sqrt(
        df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2
    )
    df["gyro_mag"] = np.zeros(n)

    out = align_session(df, sample_rate=20)
    np.testing.assert_allclose(out["accel_mag"].to_numpy(), 0.0, atol=0.1)


def test_estimate_gravity_vector_all_nan_gyro_mag_fallback():
    n = 80
    df = pd.DataFrame(
        {
            "accel_x": np.full(n, 1.0),
            "accel_y": np.full(n, -2.0),
            "accel_z": np.full(n, 3.5),
            "gyro_x": np.zeros(n),
            "gyro_y": np.zeros(n),
            "gyro_z": np.zeros(n),
            "accel_mag": np.full(n, np.sqrt(1.0**2 + 2.0**2 + 3.5**2)),
            "gyro_mag": np.full(n, np.nan),
        }
    )
    g = estimate_gravity_vector(df)
    assert np.all(np.isfinite(g))
    np.testing.assert_allclose(g, np.array([1.0, -2.0, 3.5]), atol=0.1)


def test_estimate_gravity_vector_short_dataframe_fallback_mean():
    n = 30
    df = pd.DataFrame(
        {
            "accel_x": np.full(n, 0.1),
            "accel_y": np.full(n, -0.2),
            "accel_z": np.full(n, -9.7),
            "gyro_x": np.zeros(n),
            "gyro_y": np.zeros(n),
            "gyro_z": np.zeros(n),
        }
    )
    df["accel_mag"] = np.sqrt(
        df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2
    )
    df["gyro_mag"] = np.zeros(n)

    g = estimate_gravity_vector(df, sample_rate=20)
    expected = df[["accel_x", "accel_y", "accel_z"]].mean().to_numpy(dtype=np.float64)
    np.testing.assert_allclose(g, expected, atol=0.1)


def test_build_rotation_matrix_anti_aligned_is_180_flip_about_x():
    """Upside-down phone: g along +z maps to -z via R_x(pi)."""
    R = build_rotation_matrix(np.array([0.0, 0.0, 9.81]))
    expected = np.array(
        [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]],
        dtype=np.float64,
    )
    np.testing.assert_allclose(R, expected, atol=0.1)
