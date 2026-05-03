"""Pre-enqueue validation for uploaded sessions.

Goal: reject obviously bad uploads *before* enqueueing an RQ job, so we don't
pay worker startup + pipeline cost for junk data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


SKIP_PREFIXES = ("__MACOSX", ".")


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    status: str  # "accept" | "flag" | "reject"
    errors: list[str]
    warnings: list[str]
    duration_s: float | None = None
    accel_rows: int | None = None
    gyro_rows: int | None = None
    approx_hz: float | None = None


def resolve_session_root(session_dir: Path) -> Path:
    """Return the folder containing Accelerometer.csv (handles nested ZIP layout)."""
    if (session_dir / "Accelerometer.csv").exists():
        return session_dir
    entries = [
        p
        for p in session_dir.iterdir()
        if p.name and not p.name.startswith(SKIP_PREFIXES) and p.is_dir()
    ]
    if len(entries) == 1 and (entries[0] / "Accelerometer.csv").exists():
        return entries[0]
    return session_dir


def preflight_validate_session(
    session_dir: Path,
    *,
    min_duration_s: float = 0.0,
    flag_min_duration_s: float | None = None,
    max_duration_s: float = 3 * 60 * 60.0,
    min_rows: int = 10,
    flag_min_rows: int | None = None,
    max_rows: int = 2_000_000,
) -> PreflightResult:
    """Fast checks using only the timestamp column of accel/gyro CSVs."""
    errors: list[str] = []
    warnings: list[str] = []

    root = resolve_session_root(session_dir)
    accel_path = root / "Accelerometer.csv"
    gyro_path = root / "Gyroscope.csv"

    if not accel_path.exists() or not gyro_path.exists():
        errors.append("Missing required IMU files (Accelerometer.csv and Gyroscope.csv)")
        return PreflightResult(ok=False, status="reject", errors=errors, warnings=warnings)

    def _read_time(p: Path) -> pd.Series:
        # Read as little as possible: only the timestamp column.
        df = pd.read_csv(p, usecols=["time"])
        return pd.to_numeric(df["time"], errors="coerce").dropna()

    try:
        t_acc = _read_time(accel_path)
        t_gyr = _read_time(gyro_path)
    except Exception as e:
        errors.append(f"Failed to read time column: {e}")
        return PreflightResult(ok=False, status="reject", errors=errors, warnings=warnings)

    accel_rows = int(len(t_acc))
    gyro_rows = int(len(t_gyr))

    flag_min_rows = min_rows if flag_min_rows is None else int(flag_min_rows)
    flag_min_duration_s = (
        min_duration_s if flag_min_duration_s is None else float(flag_min_duration_s)
    )

    if accel_rows < min_rows or gyro_rows < min_rows:
        errors.append(
            f"Session too short (need ≥{min_rows} rows per IMU; "
            f"got accel={accel_rows}, gyro={gyro_rows})"
        )
    elif accel_rows < flag_min_rows or gyro_rows < flag_min_rows:
        warnings.append(
            f"Borderline session length (recommended ≥{flag_min_rows} rows per IMU; "
            f"got accel={accel_rows}, gyro={gyro_rows})"
        )

    if accel_rows > max_rows or gyro_rows > max_rows:
        errors.append(
            f"Session too large (cap {max_rows} rows per IMU; "
            f"got accel={accel_rows}, gyro={gyro_rows})"
        )

    duration_s: float | None
    if accel_rows >= 2:
        duration_s = float((t_acc.iloc[-1] - t_acc.iloc[0]) / 1e9)
    elif gyro_rows >= 2:
        duration_s = float((t_gyr.iloc[-1] - t_gyr.iloc[0]) / 1e9)
    else:
        duration_s = None

    approx_hz: float | None = None
    if duration_s is not None and duration_s > 0:
        approx_hz = float(min(accel_rows, gyro_rows) / duration_s)

        if duration_s < min_duration_s:
            errors.append(
                f"Session duration too short ({duration_s:.1f}s; min {min_duration_s:.0f}s)"
            )
        elif duration_s < flag_min_duration_s:
            warnings.append(
                f"Borderline session duration ({duration_s:.1f}s; recommended ≥{flag_min_duration_s:.0f}s)"
            )
        if duration_s > max_duration_s:
            errors.append(
                f"Session duration too long ({duration_s/3600:.2f}h; max {max_duration_s/3600:.0f}h)"
            )

        # Sampling sanity: warn, don't reject (we already hard-fail on extreme sizes).
        if approx_hz < 10:
            warnings.append(f"Very low effective IMU rate (~{approx_hz:.1f} Hz)")
        elif approx_hz > 250:
            warnings.append(f"Very high effective IMU rate (~{approx_hz:.0f} Hz)")

    ok = len(errors) == 0
    status = "reject" if not ok else ("flag" if warnings else "accept")
    return PreflightResult(
        ok=ok,
        status=status,
        errors=errors,
        warnings=warnings,
        duration_s=duration_s,
        accel_rows=accel_rows,
        gyro_rows=gyro_rows,
        approx_hz=approx_hz,
    )

