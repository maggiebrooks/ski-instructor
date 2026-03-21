"""Backend confidence scoring and data quality flags.

Wraps ski/analysis modules and adds human-readable quality flags
for API responses.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ski.analysis.data_quality import evaluate_data_quality
from ski.analysis.confidence import compute_turn_confidence

# Human-readable flags for API response
LOW_GPS_CONFIDENCE = "LOW_GPS_CONFIDENCE"
HIGH_SENSOR_NOISE = "HIGH_SENSOR_NOISE"
LOW_TURN_COUNT = "LOW_TURN_COUNT"
INCOMPLETE_SESSION = "INCOMPLETE_SESSION"
UNSTABLE_SAMPLING = "UNSTABLE_SAMPLING"
HIGH_MISSING_DATA = "HIGH_MISSING_DATA"


def compute_confidence(
    df: pd.DataFrame,
    metadata: dict[str, Any],
) -> dict[str, float]:
    """Compute per-metric confidence from processed data and session metadata.

    Parameters
    ----------
    df : DataFrame
        Processed session DataFrame (with accel_*, gyro_*, speed, etc.)
        or empty DataFrame if not available.
    metadata : dict
        Session-level data: scores, summary, turn count, etc.
        Used to extract inputs for confidence rules.

    Returns
    -------
    dict
        Per-metric confidence in [0, 1], e.g.:
        {"turn_radius": 0.82, "edge_angle": 0.76, "pressure_ratio": 0.65}
    """
    data_quality = evaluate_data_quality(df)
    merged = {**metadata.get("scores", {}), **metadata.get("summary", {})}
    merged["total_turns"] = metadata.get("total_turns") or metadata.get("turns")
    merged["n_turns"] = merged.get("total_turns")
    return compute_turn_confidence(merged, data_quality)


def compute_data_quality_flags(
    data_quality: dict[str, float],
    turn_count: int | None = None,
    session_duration_s: float | None = None,
) -> list[str]:
    """Derive human-readable quality flags from data quality indicators.

    Parameters
    ----------
    data_quality : dict
        Output of evaluate_data_quality().
    turn_count : int | None
        Number of turns in session.
    session_duration_s : float | None
        Session duration in seconds.

    Returns
    -------
    list[str]
        Flags for API response, e.g. ["LOW_GPS_CONFIDENCE", "LOW_TURN_COUNT"].
    """
    flags: list[str] = []

    gps = data_quality.get("gps_accuracy", 0.5)
    if gps < 0.6:
        flags.append(LOW_GPS_CONFIDENCE)

    gyro = data_quality.get("gyro_quality", 0.5)
    missing = 1.0 - data_quality.get("missing_ratio", 0)
    if gyro < 0.5:
        flags.append(HIGH_SENSOR_NOISE)
    if missing > 0.2:
        flags.append(HIGH_MISSING_DATA)

    sampling = data_quality.get("sampling_rate_stability", 0.5)
    if sampling < 0.7:
        flags.append(UNSTABLE_SAMPLING)

    if turn_count is not None and turn_count < 5:
        flags.append(LOW_TURN_COUNT)

    if session_duration_s is not None and session_duration_s < 60:
        flags.append(INCOMPLETE_SESSION)

    return flags
