"""Turn signature visualization for exploratory technique analysis.

Approximates within-turn signal curves from per-turn summary metrics and
plots the median signature across all turns in a session.  Useful for
spotting patterns like late pressure build, abrupt spikes, inconsistent
rhythm, or excessive torso rotation.

This module is read-only and does not modify the pipeline or database.

Usage::

    from ski.analysis.turn_signature import plot_session_signature
    plot_session_signature(analyzer, "session_id_here")
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ── Outlier / quality filters ────────────────────────────────────────

_FILTERS = {
    "pelvis_peak_g_force": lambda s: s <= 3,
    "pelvis_estimated_turn_radius": lambda s: s <= 100,
    "duration_seconds": lambda s: s >= 0.2,
}

_REQUIRED_COLS = [
    "pelvis_peak_g_force",
    "pelvis_peak_angular_velocity",
    "pelvis_estimated_turn_radius",
    "duration_seconds",
]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with missing required columns or outlier values."""
    out = df.dropna(subset=_REQUIRED_COLS).copy()
    for col, pred in _FILTERS.items():
        if col in out.columns:
            out = out.loc[pred(out[col])]
    return out.reset_index(drop=True)


# ── Curve approximation ─────────────────────────────────────────────

def _bell(t: np.ndarray, peak: float) -> np.ndarray:
    """Symmetric bell curve peaking at t=0.5, scaled to *peak*."""
    return peak * np.exp(-((t - 0.5) ** 2) / 0.05)


def _build_curves(
    df: pd.DataFrame,
    num_samples: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (pressure, rotation, radius) arrays of shape (n_turns, num_samples)."""
    t = np.linspace(0, 1, num_samples)
    n = len(df)

    pressure = np.empty((n, num_samples))
    rotation = np.empty((n, num_samples))
    radius = np.empty((n, num_samples))

    for i in range(n):
        pressure[i] = _bell(t, df.iloc[i]["pelvis_peak_g_force"])
        rotation[i] = _bell(t, df.iloc[i]["pelvis_peak_angular_velocity"])
        radius[i] = df.iloc[i]["pelvis_estimated_turn_radius"]

    return pressure, rotation, radius


# ── Public API ───────────────────────────────────────────────────────

def plot_turn_signature(
    df: pd.DataFrame,
    num_samples: int = 50,
    *,
    show: bool = True,
) -> plt.Figure:
    """Plot the median turn signature for a set of turns.

    Parameters
    ----------
    df : DataFrame
        Per-turn data from ``TurnAnalyzer.load_turns()``.
    num_samples : int
        Points along the normalized 0-1 turn phase axis.
    show : bool
        Call ``plt.show()`` after building the figure.  Set to ``False``
        when saving to file or embedding in a notebook.

    Returns
    -------
    matplotlib.figure.Figure
    """
    clean = _clean(df)
    if clean.empty:
        fig, ax = plt.subplots()
        ax.text(
            0.5, 0.5, "No valid turns to plot",
            ha="center", va="center", transform=ax.transAxes,
        )
        ax.set_title("Turn Signature – No Data")
        if show:
            plt.show()
        return fig

    pressure, rotation, radius = _build_curves(clean, num_samples)

    med_pressure = np.median(pressure, axis=0)
    med_rotation = np.median(rotation, axis=0)
    med_radius = np.median(radius, axis=0)

    # Normalize each curve to 0-1 for comparable overlay
    def _norm(arr: np.ndarray) -> np.ndarray:
        lo, hi = arr.min(), arr.max()
        return (arr - lo) / (hi - lo) if hi > lo else np.full_like(arr, 0.5)

    t = np.linspace(0, 1, num_samples)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(t, _norm(med_pressure), label="Pressure (g-force)", linewidth=2)
    ax.plot(t, _norm(med_rotation), label="Rotation (angular vel)", linewidth=2)
    ax.plot(t, _norm(med_radius), label="Radius", linewidth=2, linestyle="--")

    # Shade individual turn envelopes (10th-90th percentile)
    p10_p = np.percentile(pressure, 10, axis=0)
    p90_p = np.percentile(pressure, 90, axis=0)
    ax.fill_between(t, _norm(p10_p), _norm(p90_p), alpha=0.12, color="C0")

    p10_r = np.percentile(rotation, 10, axis=0)
    p90_r = np.percentile(rotation, 90, axis=0)
    ax.fill_between(t, _norm(p10_r), _norm(p90_r), alpha=0.12, color="C1")

    ax.set_xlabel("Turn Phase")
    ax.set_ylabel("Normalized Signal Magnitude")
    ax.set_title(
        f"Turn Signature \u2013 Session Overview  ({len(clean)} turns)"
    )
    ax.legend(loc="upper right")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.05, 1.05)

    fig.tight_layout()
    if show:
        plt.show()
    return fig


def plot_session_signature(
    analyzer,
    session_id: str,
    num_samples: int = 50,
    *,
    show: bool = True,
) -> plt.Figure:
    """Convenience: load turns from the analyzer, then plot.

    Parameters
    ----------
    analyzer : TurnAnalyzer
        Must expose ``load_turns(session_ids)``.
    session_id : str
        Session to visualize.
    num_samples : int
        Points along the normalized turn phase axis.
    show : bool
        Whether to call ``plt.show()``.

    Returns
    -------
    matplotlib.figure.Figure
    """
    df = analyzer.load_turns([session_id])
    return plot_turn_signature(df, num_samples=num_samples, show=show)
