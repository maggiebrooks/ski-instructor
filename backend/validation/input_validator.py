"""Pre-pipeline validation of raw session data.

Validates required files, columns, value bounds, and sampling consistency.
Fails hard if invalid.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.contracts.schemas import ValidationResult

logger = logging.getLogger(__name__)

REQUIRED_FILES = ["Accelerometer.csv", "Gyroscope.csv"]
ACCEL_BOUND = 250.0  # m/s² (~25g) — allow spikes from bumps/impacts
GYRO_BOUND = 50.0    # rad/s
MIN_ROWS = 10
MIN_SAMPLE_INTERVAL_S = 0.001
MAX_SAMPLE_INTERVAL_S = 1.0


def validate_raw_session(path_to_session: str | Path) -> ValidationResult:
    """Validate raw session directory before pipeline execution.

    Parameters
    ----------
    path_to_session : str | Path
        Path to the extracted session folder (containing Accelerometer.csv,
        Gyroscope.csv, etc.).

    Returns
    -------
    ValidationResult
        valid=True if all checks pass; errors list non-empty if invalid.
        FAIL HARD (raise) if invalid.

    Raises
    ------
    ValueError
        When validation fails. Message includes all errors.
    """
    path = Path(path_to_session)
    errors: list[str] = []
    warnings: list[str] = []

    # --- 1. Required files exist ---
    for f in REQUIRED_FILES:
        if not (path / f).exists():
            errors.append(f"Missing required file: {f}")

    if errors:
        _fail(errors, warnings, path)

    # --- 2. Load and check columns ---
    accel_path = path / "Accelerometer.csv"
    gyro_path = path / "Gyroscope.csv"

    try:
        accel = pd.read_csv(accel_path)
        gyro = pd.read_csv(gyro_path)
    except Exception as e:
        errors.append(f"Failed to read CSV: {e}")
        _fail(errors, warnings, path)

    # Required columns: time, x, y, z (Sensor Logger format)
    required_cols = ["time", "x", "y", "z"]
    for name, df in [("Accelerometer", accel), ("Gyroscope", gyro)]:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            errors.append(f"{name}.csv missing columns: {missing}")

    if errors:
        _fail(errors, warnings, path)

    # --- 3. No completely empty columns ---
    for name, df in [("Accelerometer", accel), ("Gyroscope", gyro)]:
        for col in required_cols:
            if df[col].dropna().empty:
                errors.append(f"{name}.csv column '{col}' is empty")

    if errors:
        _fail(errors, warnings, path)

    # --- 4. Timestamp monotonicity ---
    for name, df in [("Accelerometer", accel), ("Gyroscope", gyro)]:
        t = pd.to_numeric(df["time"], errors="coerce").dropna()
        if len(t) < MIN_ROWS:
            errors.append(f"{name}.csv has fewer than {MIN_ROWS} valid rows")
        elif not t.is_monotonic_increasing:
            errors.append(f"{name}.csv timestamps are not monotonically increasing")

    if errors:
        _fail(errors, warnings, path)

    # --- 5. Sampling rate sanity ---
    for name, df in [("Accelerometer", accel), ("Gyroscope", gyro)]:
        t = pd.to_numeric(df["time"], errors="coerce").dropna()
        if len(t) < 2:
            continue
        dt_ns = np.diff(t.values)
        dt_s = dt_ns / 1e9
        dt_s = dt_s[dt_s > 0]
        if len(dt_s) > 0:
            mean_dt = float(np.mean(dt_s))
            if mean_dt < MIN_SAMPLE_INTERVAL_S:
                warnings.append(f"{name}: very high sample rate ({1/max(mean_dt,1e-6):.0f} Hz)")
            elif mean_dt > MAX_SAMPLE_INTERVAL_S:
                warnings.append(f"{name}: very low sample rate ({1/max(mean_dt,1e-6):.2f} Hz)")
            cv = float(np.std(dt_s) / mean_dt) if mean_dt > 0 else 0
            if cv > 0.5:
                warnings.append(f"{name}: high sampling irregularity (CV={cv:.2f})")

    # --- 6. Value bounds ---
    for name, df, cols, bound in [
        ("Accelerometer", accel, ["x", "y", "z"], ACCEL_BOUND),
        ("Gyroscope", gyro, ["x", "y", "z"], GYRO_BOUND),
    ]:
        for col in cols:
            vals = pd.to_numeric(df[col], errors="coerce")
            if vals.isna().any():
                errors.append(f"{name}.csv {col} contains NaN")
            if np.isinf(vals).any():
                errors.append(f"{name}.csv {col} contains Inf")
            vals = vals.dropna()
            if vals.empty:
                continue
            if (vals.abs() > bound).any():
                errors.append(
                    f"{name}.csv {col} exceeds ±{bound} (max {vals.abs().max():.1f})"
                )

    if errors:
        _fail(errors, warnings, path)

    # --- Quality score ---
    quality_score = _compute_quality_score(accel, gyro, warnings)

    result = ValidationResult(
        valid=True,
        errors=[],
        warnings=warnings,
        quality_score=quality_score,
    )

    if warnings:
        logger.warning(
            "validation_warnings",
            extra={"session_path": str(path), "warnings": warnings},
        )

    logger.info(
        "validation_passed",
        extra={"session_path": str(path), "quality_score": quality_score},
    )

    return result


def _compute_quality_score(accel: pd.DataFrame, gyro: pd.DataFrame, warnings: list[str]) -> float:
    """Compute 0-1 quality score from data characteristics."""
    score = 1.0
    # Penalize for warnings
    score -= 0.05 * min(len(warnings), 4)
    # Reward for sufficient data
    n_accel = len(accel.dropna(subset=["time", "x", "y", "z"]))
    n_gyro = len(gyro.dropna(subset=["time", "x", "y", "z"]))
    if n_accel >= 1000 and n_gyro >= 1000:
        score = min(score + 0.1, 1.0)
    return max(0.0, min(1.0, score))


def _fail(errors: list[str], warnings: list[str], path: Path) -> None:
    """Raise ValueError with validation failure details."""
    msg = f"Validation failed for {path}: " + "; ".join(errors)
    logger.error(
        "validation_failed",
        extra={"session_path": str(path), "errors": errors, "warnings": warnings},
    )
    raise ValueError(msg)
