"""Session-level diagnostics for desk physics and validation (logging-only)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_G0 = 9.81
_SAFE_RADIUS_FLOOR = 0.5


def compute_pressure_ratio_diagnostics(turns: pd.DataFrame) -> dict[str, Any]:
    """Aggregate pressure-ratio statistics for one session (desk physics pass).

    Mirrors the centripetal block in ``TurnInsights.compute_normalized_metrics``
    (same ``expected_g`` and per-turn ratio), without duplicating scoring logic.

    Parameters
    ----------
    turns
        Per-turn DataFrame (e.g. ``TurnAnalyzer.load_turns`` output). Requires
        ``pelvis_estimated_turn_radius``, ``speed_at_apex``, ``pelvis_peak_g_force``.

    Returns
    -------
    dict
        median_measured_g, median_expected_g, median_pressure_ratio,
        frac_ratio_above_1_2, frac_ratio_below_0_6 — each ``float`` or ``None``
        when undefined (empty frame, missing columns, or no valid per-turn ratios).
    """
    empty: dict[str, Any] = {
        "median_measured_g": None,
        "median_expected_g": None,
        "median_pressure_ratio": None,
        "frac_ratio_above_1_2": None,
        "frac_ratio_below_0_6": None,
    }

    if turns is None or turns.empty:
        return empty

    required = (
        "pelvis_estimated_turn_radius",
        "speed_at_apex",
        "pelvis_peak_g_force",
    )
    if any(col not in turns.columns for col in required):
        return empty

    radius = turns["pelvis_estimated_turn_radius"]
    speed = turns["speed_at_apex"]
    g_meas = turns["pelvis_peak_g_force"]

    safe_radius = radius.where(radius >= _SAFE_RADIUS_FLOOR)
    expected_g = (speed ** 2) / (safe_radius * _G0)
    expected_g = expected_g.replace([np.inf, -np.inf], np.nan)
    safe_expected = expected_g.where(expected_g > 0)
    per_turn_pr = g_meas / safe_expected
    per_turn_pr = per_turn_pr.replace([np.inf, -np.inf], np.nan)

    valid = per_turn_pr.dropna()
    if valid.empty:
        return empty

    idx = valid.index
    med_g = float(g_meas.loc[idx].median())
    med_exp = float(safe_expected.loc[idx].median())
    med_pr = float(valid.median())

    n = int(valid.shape[0])
    frac_hi = float((valid > 1.2).sum() / n)
    frac_lo = float((valid < 0.6).sum() / n)

    return {
        "median_measured_g": med_g,
        "median_expected_g": med_exp,
        "median_pressure_ratio": med_pr,
        "frac_ratio_above_1_2": frac_hi,
        "frac_ratio_below_0_6": frac_lo,
    }
