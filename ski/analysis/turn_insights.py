"""Biomechanical interpretation layer for ski turn analytics.

Computes six movement-pattern scores from per-turn DataFrames and maps them
to the Five Fundamentals of Alpine Skiing (PSIA) plus Turn Rhythm feedback.

When optional skier/ski metadata is provided, physics-based normalization
converts raw metrics into dimensionless quantities comparable across
different skiers, skis, and conditions.

Scores:
    rotary_stability, edge_consistency, pressure_management,
    turn_symmetry, turn_shape_consistency, turn_rhythm

Normalized metrics (require metadata or per-turn physics):
    normalized_turn_radius  – turn radius / ski length  (needs metadata)
    pressure_ratio          – measured g / centripetal g (per-turn physics)
    torso_rotation_ratio    – torso rotation / turn angle

No database access -- operates on DataFrames and dicts passed in by callers.

Usage::

    from ski.analysis.turn_insights import TurnInsights
    insights = TurnInsights()
    lines = insights.session_report(analyzer, "session_id_here")
    for line in lines:
        print(line)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_TURNS_FOR_SCORES = 5

# Order used to break ties when choosing the weakest movement score for coaching.
SCORE_PRIORITY = [
    "turn_rhythm",
    "turn_shape_consistency",
    "pressure_management",
    "edge_consistency",
    "rotary_stability",
    "turn_symmetry",
    "turn_efficiency",
]

METRIC_ACTION_MAP = {
    "turn_rhythm": (
        "Next run: focus on smoother, more consistent timing between turns — "
        "count a steady rhythm as you ski."
    ),
    "pressure_management": (
        "Next run: apply pressure earlier in the turn — exaggerate it at initiation."
    ),
    "edge_consistency": (
        "Next run: commit to stronger edge angles through the middle of each turn."
    ),
    "rotary_stability": (
        "Next run: reduce upper body rotation — let your skis guide the turn."
    ),
    "turn_symmetry": (
        "Next run: match your left and right turns — focus on equal weight and shape."
    ),
    "turn_shape_consistency": (
        "Next run: aim for more consistent turn shapes — avoid mixing sharp and wide turns."
    ),
    "turn_efficiency": (
        "Next run: stay balanced and flowing — avoid unnecessary skidding or braking."
    ),
}


def _generate_actionable_top_insight(scores: dict) -> str:
    """Deterministic coaching line from lowest movement score (0–1); always returns text."""
    movement = {
        k: v
        for k, v in scores.items()
        if k in SCORE_PRIORITY and v is not None
    }
    if not movement:
        return "Next run: focus on smooth, controlled skiing and consistent turns."

    worst_metric = min(movement, key=movement.get)
    worst_score = float(movement[worst_metric])

    action = METRIC_ACTION_MAP.get(
        worst_metric,
        "Next run: focus on smoother, more controlled turns overall.",
    )

    if worst_score < 0.20:
        return f"Priority fix — {action}"

    return action


def _compute_top_insight(scores: dict, *args, **kwargs) -> str:
    return _generate_actionable_top_insight(scores)


# Section titles from ``summarize_session`` / ``interpret_fundamentals`` (lowercase for matching).
_INSIGHT_SECTION_HEADERS = frozenset(
    s.lower()
    for s in (
        "Fundamental Analysis",
        "Fore/Aft Balance",
        "Foot-to-Foot Balance",
        "Rotary Control",
        "Edging Control",
        "Edge Control",
        "Pressure Control",
        "Turn Rhythm",
    )
)


def clean_insights(insights: list[str]) -> list[str]:
    """Strip headers, empty lines, and metric/debug lines from raw insight strings."""
    cleaned: list[str] = []

    for raw in insights:
        line = raw.strip()

        if not line:
            continue

        lower = line.lower()
        if lower in _INSIGHT_SECTION_HEADERS:
            continue

        if lower.startswith("turns analyzed:"):
            continue

        if "[" in line and "]" in line:
            continue

        cleaned.append(line)

    return cleaned


class TurnInsights:
    """Compute biomechanical movement scores and Five-Fundamentals + Rhythm feedback."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize_session(
        self,
        metrics: dict,
        df: pd.DataFrame | None = None,
        metadata: dict | None = None,
    ) -> list[str]:
        """Produce structured insight strings grouped by the Five Fundamentals.

        When *df* (the full per-turn DataFrame) is provided, movement scores
        are computed from the per-turn distributions.  When *df* is ``None``,
        the method returns a minimal header only.

        Parameters
        ----------
        metrics : dict
            Session-level aggregates (must contain ``total_turns``).
        df : DataFrame | None
            Full per-turn DataFrame from ``TurnAnalyzer.load_turns()``.
        metadata : dict | None
            Optional skier/ski metadata for physics-based normalization.
            Expected shape::

                {"skier": {"height_cm": …, "weight_kg": …},
                 "ski":   {"length_cm": …, "waist_mm": …},
                 "sensor": {"location": "chest"}}

            All fields optional.
        """
        if metrics.get("total_turns", 0) == 0:
            return ["No turns detected in this session."]

        total = metrics.get("total_turns", 0)
        lines: list[str] = [
            f"Turns analyzed: {total}",
            "",
            "Fundamental Analysis",
        ]

        if df is not None and not df.empty:
            scores = self.compute_movement_scores(df, metadata=metadata)
            sections = self.interpret_fundamentals(scores)
        else:
            sections = []

        for heading, bullets in sections:
            lines.append("")
            lines.append(heading)
            for bullet in bullets:
                lines.append(f"  {bullet}")

        return lines

    def session_report(
        self,
        analyzer,
        session_id: str,
        metadata: dict | None = None,
    ) -> list[str]:
        """Convenience: load turns, compute scores, and summarize.

        Parameters
        ----------
        analyzer : TurnAnalyzer
            Must expose ``load_turns`` and ``session_metrics``.
        session_id : str
            The session to analyze.
        metadata : dict | None
            Optional skier/ski metadata for physics-based normalization.
        """
        df = analyzer.load_turns([session_id])
        metrics = analyzer.session_metrics(session_id)
        return self.summarize_session(metrics, df=df, metadata=metadata)

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def compute_normalized_metrics(
        df: pd.DataFrame,
        metadata: dict | None = None,
    ) -> dict:
        """Compute physics-based normalized metrics from per-turn data.

        These dimensionless metrics enable comparison across different
        skiers and equipment by removing scale dependencies.

        Parameters
        ----------
        df : DataFrame
            Per-turn data.  Must contain ``pelvis_estimated_turn_radius``,
            ``speed_at_apex``, ``pelvis_peak_g_force``,
            ``pelvis_peak_angular_velocity``, ``duration_seconds``, and
            ``pelvis_integrated_turn_angle``.
        metadata : dict | None
            ``{"ski": {"length_cm": int}, ...}``.  Only ``ski.length_cm``
            is used today.  All fields optional.

        Returns
        -------
        dict
            ``normalized_turn_radius``  – median radius / ski length (m).
                ``None`` when ski length metadata is missing.
            ``pressure_ratio``  – median(measured_g / expected_centripetal_g).
                ~1.0 = efficient carving, <0.6 = skidding, >1.2 = aggressive.
            ``torso_rotation_ratio``  – median((ang_vel * dur) / |turn_angle|).
                <0.3 = stable upper body, >0.7 = upper-body steering.
        """
        result: dict = {
            "normalized_turn_radius": None,
            "pressure_ratio": None,
            "torso_rotation_ratio": None,
        }

        if df.empty or len(df) < MIN_TURNS_FOR_SCORES:
            return result

        def _safe_med(s: pd.Series) -> float | None:
            c = s.dropna()
            return float(c.median()) if not c.empty else None

        # -- A. Radius normalised by ski length --
        if metadata:
            ski = metadata.get("ski") or {}
            length_cm = ski.get("length_cm")
            if length_cm and length_cm > 0:
                ski_length_m = length_cm / 100
                med_radius = _safe_med(df["pelvis_estimated_turn_radius"])
                if med_radius is not None:
                    result["normalized_turn_radius"] = round(
                        med_radius / ski_length_m, 2
                    )

        # -- B. Pressure ratio (centripetal physics) --
        radius = df["pelvis_estimated_turn_radius"]
        speed = df["speed_at_apex"]
        g_meas = df["pelvis_peak_g_force"]

        safe_radius = radius.where(radius >= 0.5)
        expected_g = (speed ** 2) / (safe_radius * 9.81)
        expected_g = expected_g.replace([np.inf, -np.inf], np.nan)
        safe_expected = expected_g.where(expected_g > 0)
        per_turn_pr = g_meas / safe_expected
        per_turn_pr = per_turn_pr.replace([np.inf, -np.inf], np.nan)
        med_pr = _safe_med(per_turn_pr)
        if med_pr is not None:
            result["pressure_ratio"] = round(med_pr, 3)

        # -- C. Torso rotation relative to turn angle --
        ang_vel = df["pelvis_peak_angular_velocity"]
        duration = df["duration_seconds"]
        turn_angle = df["pelvis_integrated_turn_angle"]

        safe_angle = turn_angle.abs().replace(0, np.nan)
        torso_rot = (ang_vel * duration) / safe_angle
        torso_rot = torso_rot.replace([np.inf, -np.inf], np.nan)
        med_tr = _safe_med(torso_rot)
        if med_tr is not None:
            result["torso_rotation_ratio"] = round(med_tr, 3)

        return result

    # ------------------------------------------------------------------
    # Movement scores
    # ------------------------------------------------------------------

    @staticmethod
    def compute_movement_scores(
        turns: pd.DataFrame,
        metadata: dict | None = None,
    ) -> dict:
        """Derive six 0-1 movement scores from per-turn data.

        Assumes *turns* is already filtered (high-confidence only).
        Caller is responsible for filtering before scoring.

        Scores: rotary_stability, edge_consistency, pressure_management,
        turn_symmetry, turn_shape_consistency, turn_rhythm.

        When *metadata* is provided, physics-based normalization is used
        for pressure management (centripetal pressure ratio replaces the
        fixed 1.2 g ceiling) and the three normalized metrics are appended
        to the return dict.

        Returns a dict with the six scores plus raw sub-component values.
        All scores are ``None`` when fewer than ``MIN_TURNS_FOR_SCORES``
        turns are available.
        """
        none_result = {
            "rotary_stability": None,
            "edge_consistency": None,
            "pressure_management": None,
            "turn_symmetry": None,
            "turn_shape_consistency": None,
            "turn_rhythm": None,
            "turn_efficiency": None,
            "rotary_ratio_raw": None,
            "speed_loss_avg": None,
            "g_force_avg": None,
            "radius_cv_raw": None,
            "duration_cv_raw": None,
            "avg_turns_per_min": None,
            "normalized_turn_radius": None,
            "pressure_ratio": None,
            "torso_rotation_ratio": None,
            "left_turns": 0,
            "right_turns": 0,
            "top_insight": "Next run: focus on making smooth, controlled turns.",
        }

        if turns.empty or len(turns) == 0:
            return none_result

        if len(turns) < MIN_TURNS_FOR_SCORES:
            return none_result

        # -- Physics-based normalization --
        norm = TurnInsights.compute_normalized_metrics(turns, metadata)

        def _safe_median(series: pd.Series) -> float | None:
            clean = series.dropna()
            if clean.empty:
                return None
            return float(clean.median())

        def _safe_cv(series: pd.Series) -> float | None:
            clean = series.dropna()
            if len(clean) < 2:
                return None
            mean = clean.mean()
            if mean == 0:
                return None
            return float(clean.std() / mean)

        clip = np.clip

        # -- Raw intermediates --
        radius = turns["pelvis_estimated_turn_radius"]
        ang_vel = turns["pelvis_peak_angular_velocity"]
        g_force = turns["pelvis_peak_g_force"]
        speed_loss = turns["speed_loss_ratio"]
        edge_prog = turns["pelvis_edge_build_progressiveness"]
        radius_stab = turns["pelvis_radius_stability"]
        symmetry = turns["pelvis_symmetry"]
        turn_angle = turns["pelvis_integrated_turn_angle"]
        duration = turns["duration_seconds"]
        direction = turns["direction"]

        left_count = int((direction == "left").sum())
        right_count = int((direction == "right").sum())
        total = len(turns)

        # -- 1. Rotary stability --
        # Uses torso_rotation_ratio from the normalization layer:
        # (ang_vel * duration) / |turn_angle|.  Values near 1 mean the
        # torso rotated as much as the ski turned (steering-driven);
        # near 0 means quiet upper body (edge-driven).
        rotary_ratio_raw = norm["torso_rotation_ratio"]
        if rotary_ratio_raw is not None:
            rotary_stability = float(1 - clip(rotary_ratio_raw, 0, 1))
        else:
            rotary_stability = None

        # -- 2. Edge consistency --
        edge_parts: list[float] = []
        radius_cv_raw = _safe_cv(radius)
        if radius_cv_raw is not None:
            edge_parts.append(float(1 - clip(radius_cv_raw, 0, 1)))
        med_edge_prog = _safe_median(edge_prog)
        if med_edge_prog is not None:
            edge_parts.append(float(clip(med_edge_prog, 0, 1)))
        med_radius_stab = _safe_median(radius_stab)
        if med_radius_stab is not None:
            edge_parts.append(float(1 - clip(med_radius_stab, 0, 1)))
        edge_consistency = (
            float(np.mean(edge_parts)) if edge_parts else None
        )

        # -- 3. Pressure management --
        # When pressure_ratio (measured_g / expected_centripetal_g) is
        # available from the normalization layer, it replaces the fixed
        # 1.2 g ceiling.  Combined with speed efficiency (1 - speed_loss).
        pres_parts: list[float] = []
        g_force_avg = _safe_median(g_force)
        pressure_ratio = norm["pressure_ratio"]
        if pressure_ratio is not None:
            pres_parts.append(float(clip(pressure_ratio, 0, 1)))
        elif g_force_avg is not None:
            pres_parts.append(float(clip(g_force_avg / 1.2, 0, 1)))
        speed_loss_avg = _safe_median(speed_loss)
        speed_efficiency: float | None = None
        if speed_loss_avg is not None:
            speed_efficiency = float(1 - clip(speed_loss_avg, 0, 1))
            pres_parts.append(speed_efficiency)
        pressure_management = (
            float(np.mean(pres_parts)) if pres_parts else None
        )

        # -- 4. Turn symmetry --
        sym_parts: list[float] = []
        if total > 0:
            turn_balance = abs(left_count - right_count) / total
            sym_parts.append(float(1 - clip(turn_balance, 0, 1)))
        med_symmetry = _safe_median(symmetry)
        if med_symmetry is not None:
            sym_parts.append(float(clip(med_symmetry, 0, 1)))
        avg_radius = float(radius.dropna().mean()) if not radius.dropna().empty else None
        if avg_radius and avg_radius > 0:
            left_radius = radius[direction == "left"].dropna()
            right_radius = radius[direction == "right"].dropna()
            if not left_radius.empty and not right_radius.empty:
                radius_diff = abs(left_radius.mean() - right_radius.mean())
                sym_parts.append(
                    float(1 - clip(radius_diff / avg_radius, 0, 1))
                )
        turn_symmetry_score = (
            float(np.mean(sym_parts)) if sym_parts else None
        )

        # -- 5. Turn shape consistency --
        shape_parts: list[float] = []
        if radius_cv_raw is not None:
            shape_parts.append(float(1 - clip(radius_cv_raw, 0, 1)))
        angle_cv = _safe_cv(turn_angle)
        if angle_cv is not None:
            shape_parts.append(float(1 - clip(angle_cv, 0, 1)))
        turn_shape_consistency = (
            float(np.mean(shape_parts)) if shape_parts else None
        )

        # -- 6. Turn rhythm --
        duration_cv_raw = _safe_cv(duration)
        total_duration = duration.dropna().sum()
        avg_turns_per_min: float | None = None
        if total_duration > 0:
            avg_turns_per_min = round(
                float(len(duration.dropna()) / (total_duration / 60)), 1
            )
        if duration_cv_raw is not None:
            turn_rhythm = float(1 - clip(duration_cv_raw, 0, 1))
        else:
            turn_rhythm = None

        result = {
            "rotary_stability": (
                round(rotary_stability, 2) if rotary_stability is not None else None
            ),
            "edge_consistency": (
                round(edge_consistency, 2) if edge_consistency is not None else None
            ),
            "pressure_management": (
                round(pressure_management, 2) if pressure_management is not None else None
            ),
            "turn_symmetry": (
                round(turn_symmetry_score, 2) if turn_symmetry_score is not None else None
            ),
            "turn_shape_consistency": (
                round(turn_shape_consistency, 2) if turn_shape_consistency is not None else None
            ),
            "rotary_ratio_raw": (
                round(rotary_ratio_raw, 3) if rotary_ratio_raw is not None else None
            ),
            "speed_loss_avg": (
                round(speed_loss_avg, 3) if speed_loss_avg is not None else None
            ),
            "g_force_avg": (
                round(g_force_avg, 2) if g_force_avg is not None else None
            ),
            "turn_rhythm": (
                round(turn_rhythm, 2) if turn_rhythm is not None else None
            ),
            "turn_efficiency": (
                round(speed_efficiency, 2) if speed_efficiency is not None else None
            ),
            "radius_cv_raw": (
                round(radius_cv_raw, 2) if radius_cv_raw is not None else None
            ),
            "duration_cv_raw": (
                round(duration_cv_raw, 2) if duration_cv_raw is not None else None
            ),
            "avg_turns_per_min": avg_turns_per_min,
            "normalized_turn_radius": norm["normalized_turn_radius"],
            "pressure_ratio": norm["pressure_ratio"],
            "torso_rotation_ratio": norm["torso_rotation_ratio"],
            "left_turns": left_count,
            "right_turns": right_count,
        }
        result["top_insight"] = _compute_top_insight(result)
        return result

    # ------------------------------------------------------------------
    # Fundamental interpretation
    # ------------------------------------------------------------------

    @staticmethod
    def interpret_fundamentals(
        scores: dict,
        metadata: dict | None = None,
    ) -> list[tuple[str, list[str]]]:
        """Convert movement scores into Five-Fundamentals feedback.

        Parameters
        ----------
        scores : dict
            Output of ``compute_movement_scores()``.
        metadata : dict | None
            Reserved for future normalization (skier height/weight,
            ski length/waist).  Currently unused.

        Returns
        -------
        list[tuple[str, list[str]]]
            ``(heading, [bullet_strings])`` tuples.
        """
        # Future: use metadata to normalize radius by ski length,
        # g-force by skier weight, etc.

        sections: list[tuple[str, list[str]]] = []

        pm = scores.get("pressure_management")
        if pm is not None:
            if pm < 0.3:
                text = (
                    "You may be skiing slightly aft, with limited pressure "
                    "engagement through the ski."
                )
            elif pm <= 0.6:
                text = "You maintain moderate fore/aft pressure through turns."
            else:
                text = (
                    "You maintain strong fore/aft pressure through the turn."
                )
            vals = [f"pressure management: {pm:.2f}"]
            sl = scores.get("speed_loss_avg")
            if sl is not None:
                vals.append(f"avg speed loss: {sl * 100:.1f}%")
            sections.append(("Fore/Aft Balance", [text, f"[{', '.join(vals)}]"]))

        ts = scores.get("turn_symmetry")
        if ts is not None:
            if ts < 0.4:
                text = (
                    "You show a strong bias toward one turn direction, "
                    "suggesting uneven weight distribution."
                )
            elif ts <= 0.7:
                text = (
                    "There is a slight imbalance in how you weight turns "
                    "between sides."
                )
            else:
                text = "Your left and right turns are well balanced."
            vals = [f"symmetry: {ts:.2f}"]
            left = scores.get("left_turns")
            right = scores.get("right_turns")
            if left is not None:
                vals.append(f"L: {left}")
            if right is not None:
                vals.append(f"R: {right}")
            sections.append(("Foot-to-Foot Balance", [text, f"[{', '.join(vals)}]"]))

        rs = scores.get("rotary_stability")
        if rs is not None:
            if rs < 0.4:
                text = (
                    "Your turns involve significant upper body rotation, "
                    "suggesting steering-driven turns."
                )
            elif rs <= 0.7:
                text = "You apply moderate rotary input to guide turns."
            else:
                text = (
                    "Your turns show minimal upper body rotation, "
                    "indicating edge-driven technique."
                )
            vals = [f"rotary stability: {rs:.2f}"]
            rr = scores.get("rotary_ratio_raw")
            if rr is not None:
                vals.append(f"rotary ratio: {rr:.3f}")
            sections.append(("Rotary Control", [text, f"[{', '.join(vals)}]"]))

        ec = scores.get("edge_consistency")
        if ec is not None:
            if ec < 0.4:
                text = (
                    "Edge engagement varies significantly, suggesting "
                    "inconsistent carving."
                )
            elif ec <= 0.7:
                text = "You maintain moderate edging control through turns."
            else:
                text = (
                    "You create consistent edge-driven turns with "
                    "smooth engagement."
                )
            vals = [f"edge consistency: {ec:.2f}"]
            rcv = scores.get("radius_cv_raw")
            if rcv is not None:
                vals.append(f"radius CV: {rcv:.2f}")
            sections.append(("Edging Control", [text, f"[{', '.join(vals)}]"]))

        if pm is not None and ec is not None:
            combined = (pm + ec) / 2
            if combined < 0.4:
                text = (
                    "Limited pressure build suggests light ski bending "
                    "through turns."
                )
            elif combined <= 0.7:
                text = "You maintain consistent pressure control."
            else:
                text = (
                    "You generate strong pressure through the ski, "
                    "indicating active technique."
                )
            vals = [f"pressure: {combined:.2f}"]
            gf = scores.get("g_force_avg")
            if gf is not None:
                vals.append(f"avg g-force: {gf:.2f} g")
            sections.append(("Pressure Control", [text, f"[{', '.join(vals)}]"]))
        elif pm is not None:
            gf = scores.get("g_force_avg")
            if pm < 0.4:
                text = (
                    "Limited pressure build suggests light ski bending "
                    "through turns."
                )
            elif pm <= 0.7:
                text = "You maintain consistent pressure control."
            else:
                text = (
                    "You generate strong pressure through the ski, "
                    "indicating active technique."
                )
            vals = [f"pressure: {pm:.2f}"]
            if gf is not None:
                vals.append(f"avg g-force: {gf:.2f} g")
            sections.append(("Pressure Control", [text, f"[{', '.join(vals)}]"]))

        tr = scores.get("turn_rhythm")
        if tr is not None:
            if tr < 0.4:
                text = (
                    "Your turns vary significantly in rhythm, suggesting "
                    "inconsistent timing between turns."
                )
            elif tr <= 0.7:
                text = (
                    "Your turn rhythm is moderately consistent with some "
                    "variation in cadence."
                )
            else:
                text = (
                    "You maintain a steady turn rhythm, indicating strong "
                    "timing and flow."
                )
            vals = [f"rhythm: {tr:.2f}"]
            dcv = scores.get("duration_cv_raw")
            if dcv is not None:
                vals.append(f"duration CV: {dcv:.2f}")
            tpm = scores.get("avg_turns_per_min")
            if tpm is not None:
                vals.append(f"turns/min: {tpm:.1f}")
            sections.append(("Turn Rhythm", [text, f"[{', '.join(vals)}]"]))

        return sections
