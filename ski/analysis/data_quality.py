"""Data quality evaluation for a preprocessed session DataFrame.

Inspects sensor columns to produce quality indicators in [0, 1] that
feed into the per-metric confidence model.  All computations are
deterministic -- no ML, no randomness.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_SENSOR_COLUMNS = [
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "speed", "roll", "pitch", "yaw",
]


def evaluate_data_quality(df: pd.DataFrame) -> dict:
    """Assess data quality of a preprocessed session DataFrame.

    Parameters
    ----------
    df : DataFrame
        Must contain a ``seconds`` column and ideally the standard
        sensor columns (accel_*, gyro_*, speed, roll, pitch, yaw).

    Returns
    -------
    dict
        Keys: ``gps_accuracy``, ``sampling_rate_stability``,
        ``missing_ratio``, ``gyro_quality``, ``overall_quality``.
        All values in [0, 1].
    """
    result = {
        "gps_accuracy": 0.0,
        "sampling_rate_stability": 0.0,
        "missing_ratio": 1.0,
        "gyro_quality": 0.0,
        "overall_quality": 0.0,
    }

    if df is None or df.empty:
        return result

    # --- GPS accuracy ---
    gps_accuracy = _compute_gps_accuracy(df)

    # --- Sampling rate stability ---
    sampling_stability = _compute_sampling_stability(df)

    # --- Missing data ratio (inverted: 1 = no missing) ---
    present_cols = [c for c in _SENSOR_COLUMNS if c in df.columns]
    if present_cols:
        missing_frac = float(df[present_cols].isna().mean().mean())
    else:
        missing_frac = 1.0
    missing_quality = 1.0 - missing_frac

    # --- Gyro quality ---
    gyro_quality = _compute_gyro_quality(df)

    # --- Overall (weighted mean) ---
    weights = {
        "gps_accuracy": 0.30,
        "sampling_rate_stability": 0.25,
        "missing_ratio": 0.20,
        "gyro_quality": 0.25,
    }
    scores = {
        "gps_accuracy": gps_accuracy,
        "sampling_rate_stability": sampling_stability,
        "missing_ratio": missing_quality,
        "gyro_quality": gyro_quality,
    }
    overall = sum(scores[k] * weights[k] for k in weights)

    return {
        "gps_accuracy": round(float(np.clip(gps_accuracy, 0, 1)), 4),
        "sampling_rate_stability": round(float(np.clip(sampling_stability, 0, 1)), 4),
        "missing_ratio": round(float(np.clip(missing_quality, 0, 1)), 4),
        "gyro_quality": round(float(np.clip(gyro_quality, 0, 1)), 4),
        "overall_quality": round(float(np.clip(overall, 0, 1)), 4),
    }


def _compute_gps_accuracy(df: pd.DataFrame) -> float:
    """Fraction of valid speed readings, penalised by noise at low speed."""
    if "speed" not in df.columns:
        return 0.0

    speed = df["speed"].dropna()
    if speed.empty:
        return 0.0

    valid_frac = float((speed >= 0).sum() / len(speed))

    idle = speed[speed < 0.5]
    if len(idle) > 5:
        idle_noise_penalty = float(np.clip(idle.std() / 0.5, 0, 0.3))
    else:
        idle_noise_penalty = 0.0

    return float(np.clip(valid_frac - idle_noise_penalty, 0, 1))


def _compute_sampling_stability(df: pd.DataFrame) -> float:
    """1 - CV of inter-sample intervals.  Detects dropped samples."""
    if "seconds" not in df.columns or len(df) < 3:
        return 0.0

    dt = np.diff(df["seconds"].values)
    dt = dt[dt > 0]
    if len(dt) < 2:
        return 0.0

    mean_dt = float(np.mean(dt))
    if mean_dt <= 0:
        return 0.0

    cv = float(np.std(dt) / mean_dt)
    return float(np.clip(1.0 - cv, 0, 1))


def _compute_gyro_quality(df: pd.DataFrame) -> float:
    """Signal-to-noise proxy from gyro magnitude distribution.

    A quality gyro signal has a clear dynamic range above its noise floor.
    """
    if "gyro_z" not in df.columns:
        return 0.0

    gz = df["gyro_z"].dropna().values
    if len(gz) < 10:
        return 0.0

    mag = np.abs(gz)
    noise_floor = float(np.percentile(mag, 10))
    signal_peak = float(np.percentile(mag, 95))

    if signal_peak < 1e-6:
        return 0.0

    snr = (signal_peak - noise_floor) / signal_peak
    return float(np.clip(snr, 0, 1))
