"""Read-only analytics layer on top of the ski SQLite database.

Usage::

    analyzer = TurnAnalyzer("data/ski.db")
    metrics = analyzer.session_metrics("White_River_..._2026-02-22_17-03-00")
    comparison = analyzer.compare_sessions([session_a, session_b])
"""

import sqlite3

import pandas as pd


_TURN_COLUMNS = [
    "r.session_id",
    "t.run_id",
    "t.direction",
    "t.duration_seconds",
    "t.speed_at_apex",
    "t.speed_loss_ratio",
    "t.pelvis_integrated_turn_angle",
    "t.pelvis_peak_angular_velocity",
    "t.pelvis_max_roll_angle",
    "t.pelvis_estimated_turn_radius",
    "t.pelvis_peak_g_force",
    "t.pelvis_symmetry",
    "t.pelvis_edge_build_progressiveness",
    "t.pelvis_radius_stability",
]

_BASE_SQL = f"""
    SELECT {', '.join(_TURN_COLUMNS)}
    FROM turns t
    JOIN runs r ON t.run_id = r.run_id
"""


class TurnAnalyzer:
    """Compute analytics from persisted turn data in ski.db."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Core loader — all SQL lives here
    # ------------------------------------------------------------------

    def load_turns(self, session_ids: list[str] | None = None) -> pd.DataFrame:
        """Load turns from the database, optionally filtered by session.

        Parameters
        ----------
        session_ids : list[str] | None
            When provided, only turns belonging to these sessions are
            returned.  When ``None``, all turns are loaded.

        Returns
        -------
        pd.DataFrame
            One row per turn with session_id, run_id, direction, and
            all pelvis / speed metrics.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            if session_ids is None:
                df = pd.read_sql_query(_BASE_SQL, conn)
            else:
                placeholders = ", ".join("?" for _ in session_ids)
                sql = f"{_BASE_SQL} WHERE r.session_id IN ({placeholders})"
                df = pd.read_sql_query(sql, conn, params=session_ids)
        finally:
            conn.close()
        return df

    # ------------------------------------------------------------------
    # Per-session metrics
    # ------------------------------------------------------------------

    def session_metrics(self, session_id: str) -> dict:
        """Compute aggregate turn metrics for a single session.

        Returns a dict with total counts, averages, and L/R balance.
        If the session has no turns, numeric values are ``None``.
        """
        df = self.load_turns([session_id])
        return self._compute_metrics(df, session_id)

    # ------------------------------------------------------------------
    # Per-run metrics
    # ------------------------------------------------------------------

    def run_metrics(self, session_id: str) -> pd.DataFrame:
        """Compute per-run aggregate metrics for a single session.

        Returns a DataFrame with one row per run.  If the session has
        no turns, returns an empty DataFrame.
        """
        df = self.load_turns([session_id])
        if df.empty:
            return pd.DataFrame()

        return (
            df.groupby("run_id")
            .agg(
                turn_count=("direction", "size"),
                avg_turn_radius=("pelvis_estimated_turn_radius", "mean"),
                avg_speed_at_apex=("speed_at_apex", "mean"),
                avg_peak_ang_vel=("pelvis_peak_angular_velocity", "mean"),
                avg_g_force=("pelvis_peak_g_force", "mean"),
            )
            .round(2)
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Cross-session comparison
    # ------------------------------------------------------------------

    def compare_sessions(self, session_ids: list[str]) -> pd.DataFrame:
        """Compute the same metrics for multiple sessions side-by-side.

        Returns a DataFrame with one row per session.
        """
        df = self.load_turns(session_ids)
        if df.empty:
            return pd.DataFrame()

        rows = []
        for sid, group in df.groupby("session_id"):
            rows.append(self._compute_metrics(group, str(sid)))
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Shared computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(df: pd.DataFrame, session_id: str) -> dict:
        if df.empty:
            return {
                "session_id": session_id,
                "total_turns": 0,
                "avg_turn_radius": None,
                "radius_std": None,
                "radius_cv": None,
                "avg_peak_ang_vel": None,
                "avg_speed_at_apex": None,
                "avg_g_force": None,
                "avg_symmetry": None,
                "left_turns": 0,
                "right_turns": 0,
                "turn_balance": None,
            }

        direction_counts = df["direction"].value_counts()
        avg_radius = float(df["pelvis_estimated_turn_radius"].mean())
        std_radius = float(df["pelvis_estimated_turn_radius"].std())
        left = int(direction_counts.get("left", 0))
        right = int(direction_counts.get("right", 0))
        total = len(df)

        return {
            "session_id": session_id,
            "total_turns": total,
            "avg_turn_radius": round(avg_radius, 2),
            "radius_std": round(std_radius, 2),
            "radius_cv": round(std_radius / avg_radius, 2) if avg_radius != 0 else None,
            "avg_peak_ang_vel": round(float(df["pelvis_peak_angular_velocity"].mean()), 2),
            "avg_speed_at_apex": round(float(df["speed_at_apex"].mean()), 2),
            "avg_g_force": round(float(df["pelvis_peak_g_force"].mean()), 2),
            "avg_symmetry": round(float(df["pelvis_symmetry"].mean()), 2),
            "left_turns": left,
            "right_turns": right,
            "turn_balance": round(abs(left - right) / total, 2) if total > 0 else None,
        }
