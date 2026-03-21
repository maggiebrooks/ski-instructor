"""Unit tests for the biomechanical TurnInsights layer.

Run with:  python -m pytest tests/test_turn_insights.py -v
"""

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ski.analysis.turn_insights import (
    TurnInsights,
    MIN_TURNS_FOR_SCORES,
    clean_insights,
)


@pytest.fixture()
def insights():
    return TurnInsights()


def _make_turn_df(n=50, **overrides):
    """Build a synthetic per-turn DataFrame with controllable columns."""
    rng = np.random.default_rng(42)
    data = {
        "session_id": ["sess"] * n,
        "run_id": [f"run_{i % 3}" for i in range(n)],
        "direction": ["left" if i % 2 == 0 else "right" for i in range(n)],
        "duration_seconds": rng.uniform(0.8, 2.5, n),
        "speed_at_apex": rng.uniform(15, 40, n),
        "speed_loss_ratio": rng.uniform(0.05, 0.3, n),
        "pelvis_integrated_turn_angle": rng.uniform(20, 80, n),
        "pelvis_peak_angular_velocity": rng.uniform(0.5, 2.0, n),
        "pelvis_max_roll_angle": rng.uniform(5, 30, n),
        "pelvis_estimated_turn_radius": rng.uniform(5, 20, n),
        "pelvis_peak_g_force": rng.uniform(0.2, 1.2, n),
        "pelvis_symmetry": rng.uniform(0.5, 1.0, n),
        "pelvis_edge_build_progressiveness": rng.uniform(0.1, 0.8, n),
        "pelvis_radius_stability": rng.uniform(0.1, 0.6, n),
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _flat(result: list[str]) -> str:
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Zero-turn guard
# ---------------------------------------------------------------------------

class TestZeroTurnGuard:
    def test_zero_turns(self, insights):
        result = insights.summarize_session({"total_turns": 0})
        assert result == ["No turns detected in this session."]

    def test_missing_total_turns_key(self, insights):
        result = insights.summarize_session({"session_id": "x"})
        assert result == ["No turns detected in this session."]


# ---------------------------------------------------------------------------
# compute_normalized_metrics
# ---------------------------------------------------------------------------

class TestComputeNormalizedMetrics:
    def test_empty_df_returns_all_none(self, insights):
        result = insights.compute_normalized_metrics(pd.DataFrame())
        assert result == {
            "normalized_turn_radius": None,
            "pressure_ratio": None,
            "torso_rotation_ratio": None,
        }

    def test_too_few_turns_returns_all_none(self, insights):
        df = _make_turn_df(n=3)
        result = insights.compute_normalized_metrics(df)
        assert result["pressure_ratio"] is None

    def test_pressure_ratio_computed_without_metadata(self, insights):
        df = _make_turn_df()
        result = insights.compute_normalized_metrics(df)
        assert result["pressure_ratio"] is not None
        assert result["pressure_ratio"] > 0

    def test_torso_rotation_ratio_computed_without_metadata(self, insights):
        df = _make_turn_df()
        result = insights.compute_normalized_metrics(df)
        assert result["torso_rotation_ratio"] is not None
        assert result["torso_rotation_ratio"] > 0

    def test_normalized_radius_requires_metadata(self, insights):
        df = _make_turn_df()
        result = insights.compute_normalized_metrics(df, metadata=None)
        assert result["normalized_turn_radius"] is None

    def test_normalized_radius_with_ski_length(self, insights):
        df = _make_turn_df(
            pelvis_estimated_turn_radius=np.full(50, 10.0),
        )
        meta = {"ski": {"length_cm": 164}}
        result = insights.compute_normalized_metrics(df, metadata=meta)
        assert result["normalized_turn_radius"] is not None
        expected = round(10.0 / 1.64, 2)
        assert result["normalized_turn_radius"] == expected

    def test_normalized_radius_missing_length_key(self, insights):
        df = _make_turn_df()
        meta = {"ski": {}}
        result = insights.compute_normalized_metrics(df, metadata=meta)
        assert result["normalized_turn_radius"] is None

    def test_pressure_ratio_known_physics(self, insights):
        # speed=20 m/s, radius=10 m -> expected_g = 400/(10*9.81) ≈ 4.08
        # measured_g = 0.8 -> ratio = 0.8/4.08 ≈ 0.196
        df = _make_turn_df(
            speed_at_apex=np.full(50, 20.0),
            pelvis_estimated_turn_radius=np.full(50, 10.0),
            pelvis_peak_g_force=np.full(50, 0.8),
        )
        result = insights.compute_normalized_metrics(df)
        assert result["pressure_ratio"] is not None
        assert abs(result["pressure_ratio"] - 0.196) < 0.01

    def test_torso_rotation_known_values(self, insights):
        # ang_vel=1.0, duration=2.0, turn_angle=40 -> ratio = 2/40 = 0.05
        df = _make_turn_df(
            pelvis_peak_angular_velocity=np.full(50, 1.0),
            duration_seconds=np.full(50, 2.0),
            pelvis_integrated_turn_angle=np.full(50, 40.0),
        )
        result = insights.compute_normalized_metrics(df)
        assert result["torso_rotation_ratio"] == 0.05

    def test_zero_radius_excluded(self, insights):
        df = _make_turn_df(
            pelvis_estimated_turn_radius=np.full(50, 0.0),
        )
        result = insights.compute_normalized_metrics(df)
        assert result["pressure_ratio"] is None

    def test_zero_turn_angle_excluded(self, insights):
        df = _make_turn_df(
            pelvis_integrated_turn_angle=np.full(50, 0.0),
        )
        result = insights.compute_normalized_metrics(df)
        assert result["torso_rotation_ratio"] is None


# ---------------------------------------------------------------------------
# compute_movement_scores
# ---------------------------------------------------------------------------

class TestComputeMovementScores:
    def test_returns_all_six_scores(self, insights):
        df = _make_turn_df()
        scores = insights.compute_movement_scores(df)
        for key in [
            "rotary_stability",
            "edge_consistency",
            "pressure_management",
            "turn_symmetry",
            "turn_shape_consistency",
            "turn_rhythm",
        ]:
            assert key in scores
            assert scores[key] is not None
            assert 0 <= scores[key] <= 1, f"{key} out of range: {scores[key]}"

    def test_too_few_turns_returns_none(self, insights):
        df = _make_turn_df(n=3)
        scores = insights.compute_movement_scores(df)
        for key in [
            "rotary_stability",
            "edge_consistency",
            "pressure_management",
            "turn_symmetry",
            "turn_shape_consistency",
            "turn_rhythm",
            "turn_efficiency",
        ]:
            assert scores[key] is None

    def test_empty_df_returns_none(self, insights):
        df = pd.DataFrame()
        scores = insights.compute_movement_scores(df)
        assert scores["rotary_stability"] is None

    def test_high_torso_rotation_low_rotary_stability(self, insights):
        # ang_vel * duration / turn_angle = 3.0 * 2.0 / 40 = 0.15
        # But with very high ang_vel relative to turn angle:
        # 5.0 * 2.0 / 5.0 = 2.0 -> clamped to 1.0 -> stability = 0.0
        df = _make_turn_df(
            pelvis_peak_angular_velocity=np.full(50, 5.0),
            duration_seconds=np.full(50, 2.0),
            pelvis_integrated_turn_angle=np.full(50, 5.0),
        )
        scores = insights.compute_movement_scores(df)
        assert scores["rotary_stability"] is not None
        assert scores["rotary_stability"] == 0.0

    def test_low_torso_rotation_high_rotary_stability(self, insights):
        # 0.1 * 1.0 / 60 = 0.0017 -> stability ~ 1.0
        df = _make_turn_df(
            pelvis_peak_angular_velocity=np.full(50, 0.1),
            duration_seconds=np.full(50, 1.0),
            pelvis_integrated_turn_angle=np.full(50, 60.0),
        )
        scores = insights.compute_movement_scores(df)
        assert scores["rotary_stability"] is not None
        assert scores["rotary_stability"] >= 0.95

    def test_low_radius_cv_high_edge_consistency(self, insights):
        df = _make_turn_df(
            pelvis_estimated_turn_radius=np.full(50, 10.0),
            pelvis_edge_build_progressiveness=np.full(50, 0.9),
            pelvis_radius_stability=np.full(50, 0.05),
        )
        scores = insights.compute_movement_scores(df)
        assert scores["edge_consistency"] is not None
        assert scores["edge_consistency"] > 0.7

    def test_balanced_lr_high_symmetry(self, insights):
        directions = ["left", "right"] * 25
        df = _make_turn_df(direction=directions)
        scores = insights.compute_movement_scores(df)
        assert scores["turn_symmetry"] is not None
        assert scores["turn_symmetry"] > 0.5

    def test_unbalanced_lr_low_symmetry(self, insights):
        directions = ["left"] * 45 + ["right"] * 5
        df = _make_turn_df(direction=directions)
        scores = insights.compute_movement_scores(df)
        balanced_df = _make_turn_df(direction=["left", "right"] * 25)
        balanced_scores = insights.compute_movement_scores(balanced_df)
        assert scores["turn_symmetry"] < balanced_scores["turn_symmetry"]

    def test_nan_columns_handled(self, insights):
        df = _make_turn_df()
        df["pelvis_edge_build_progressiveness"] = np.nan
        df["pelvis_radius_stability"] = np.nan
        scores = insights.compute_movement_scores(df)
        assert scores["edge_consistency"] is not None

    def test_raw_components_present(self, insights):
        df = _make_turn_df()
        scores = insights.compute_movement_scores(df)
        assert "rotary_ratio_raw" in scores
        assert "speed_loss_avg" in scores
        assert "g_force_avg" in scores
        assert "radius_cv_raw" in scores
        assert "duration_cv_raw" in scores
        assert "avg_turns_per_min" in scores
        assert "turn_efficiency" in scores
        assert "normalized_turn_radius" in scores
        assert "pressure_ratio" in scores
        assert "torso_rotation_ratio" in scores
        assert "left_turns" in scores
        assert "right_turns" in scores

    def test_high_pressure_ratio_high_pressure(self, insights):
        # Low speed + large radius -> small expected_g -> high pressure ratio
        # expected_g = 5²/(10*9.81) ≈ 0.255, ratio = 0.5/0.255 ≈ 1.96 -> clip 1.0
        df = _make_turn_df(
            speed_at_apex=np.full(50, 5.0),
            pelvis_estimated_turn_radius=np.full(50, 10.0),
            pelvis_peak_g_force=np.full(50, 0.5),
            speed_loss_ratio=np.full(50, 0.05),
        )
        scores = insights.compute_movement_scores(df)
        assert scores["pressure_management"] is not None
        assert scores["pressure_management"] > 0.8

    def test_low_pressure_ratio_low_pressure(self, insights):
        # High speed + small radius -> large expected_g -> low pressure ratio
        # expected_g = 30²/(5*9.81) ≈ 18.3, ratio = 0.1/18.3 ≈ 0.005
        df = _make_turn_df(
            speed_at_apex=np.full(50, 30.0),
            pelvis_estimated_turn_radius=np.full(50, 5.0),
            pelvis_peak_g_force=np.full(50, 0.1),
            speed_loss_ratio=np.full(50, 0.9),
        )
        scores = insights.compute_movement_scores(df)
        assert scores["pressure_management"] is not None
        assert scores["pressure_management"] < 0.2

    def test_consistent_duration_high_rhythm(self, insights):
        df = _make_turn_df(duration_seconds=np.full(50, 1.5))
        scores = insights.compute_movement_scores(df)
        assert scores["turn_rhythm"] is not None
        assert scores["turn_rhythm"] > 0.95

    def test_variable_duration_low_rhythm(self, insights):
        durations = np.concatenate([np.full(25, 0.5), np.full(25, 5.0)])
        df = _make_turn_df(duration_seconds=durations)
        scores = insights.compute_movement_scores(df)
        assert scores["turn_rhythm"] is not None
        assert scores["turn_rhythm"] < 0.5

    def test_avg_turns_per_min_calculated(self, insights):
        df = _make_turn_df(duration_seconds=np.full(50, 2.0))
        scores = insights.compute_movement_scores(df)
        assert scores["avg_turns_per_min"] == pytest.approx(30.0, abs=0.1)

    def test_low_speed_loss_high_efficiency(self, insights):
        df = _make_turn_df(speed_loss_ratio=np.full(50, 0.05))
        scores = insights.compute_movement_scores(df)
        assert scores["turn_efficiency"] is not None
        assert scores["turn_efficiency"] >= 0.95

    def test_high_speed_loss_low_efficiency(self, insights):
        df = _make_turn_df(speed_loss_ratio=np.full(50, 0.8))
        scores = insights.compute_movement_scores(df)
        assert scores["turn_efficiency"] is not None
        assert scores["turn_efficiency"] <= 0.2

    def test_zero_turn_angle_handled(self, insights):
        df = _make_turn_df(pelvis_integrated_turn_angle=np.full(50, 0.0))
        scores = insights.compute_movement_scores(df)
        assert scores["rotary_stability"] is None

    def test_no_metadata_backward_compatible(self, insights):
        df = _make_turn_df()
        scores = insights.compute_movement_scores(df)
        assert scores["normalized_turn_radius"] is None

    def test_metadata_populates_normalized_radius(self, insights):
        df = _make_turn_df(
            pelvis_estimated_turn_radius=np.full(50, 10.0),
        )
        meta = {"ski": {"length_cm": 164}}
        scores = insights.compute_movement_scores(df, metadata=meta)
        assert scores["normalized_turn_radius"] is not None
        assert scores["normalized_turn_radius"] == round(10.0 / 1.64, 2)

    def test_pressure_ratio_used_in_pressure_score(self, insights):
        df = _make_turn_df(
            speed_at_apex=np.full(50, 10.0),
            pelvis_estimated_turn_radius=np.full(50, 10.0),
            pelvis_peak_g_force=np.full(50, 0.5),
            speed_loss_ratio=np.full(50, 0.1),
        )
        scores_no_meta = insights.compute_movement_scores(df)
        scores_with_meta = insights.compute_movement_scores(
            df, metadata={"ski": {"length_cm": 164}}
        )
        assert scores_no_meta["pressure_ratio"] == scores_with_meta["pressure_ratio"]
        assert scores_no_meta["pressure_management"] is not None
        assert scores_with_meta["pressure_management"] is not None

    def test_none_result_includes_normalized_keys(self, insights):
        df = _make_turn_df(n=3)
        scores = insights.compute_movement_scores(df)
        assert "normalized_turn_radius" in scores
        assert "pressure_ratio" in scores
        assert "torso_rotation_ratio" in scores
        assert scores["normalized_turn_radius"] is None
        assert scores["pressure_ratio"] is None
        assert scores["torso_rotation_ratio"] is None
        assert scores.get("top_insight") == (
            "Next run: focus on making smooth, controlled turns."
        )

    def test_top_insight_targets_weakest_score(self, insights):
        """Lowest movement score drives coaching top_insight."""
        df = _make_turn_df(
            duration_seconds=np.full(50, 2.0),
            pelvis_integrated_turn_angle=np.full(50, 45.0),
        )
        scores = insights.compute_movement_scores(df)
        assert scores.get("top_insight") is not None
        assert isinstance(scores["top_insight"], str)
        assert len(scores["top_insight"]) > 20


# ---------------------------------------------------------------------------
# interpret_fundamentals
# ---------------------------------------------------------------------------

class TestInterpretFundamentals:
    def test_low_pressure_aft_feedback(self, insights):
        scores = {
            "pressure_management": 0.2,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.6,
            "turn_efficiency": 0.7,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.3,
            "g_force_avg": 0.3,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.4,
            "avg_turns_per_min": 20.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.5,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        flat = "\n".join(b for _, bs in sections for b in bs)
        assert "aft" in flat.lower()

    def test_high_edge_consistent_feedback(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.85,
            "turn_shape_consistency": 0.8,
            "turn_rhythm": 0.6,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.8,
            "radius_cv_raw": 0.15,
            "duration_cv_raw": 0.4,
            "avg_turns_per_min": 20.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        flat = "\n".join(b for _, bs in sections for b in bs)
        assert "consistent edge-driven" in flat

    def test_high_rotary_stability_edge_driven(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.85,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.6,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.15,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.5,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.4,
            "avg_turns_per_min": 20.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.15,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        flat = "\n".join(b for _, bs in sections for b in bs)
        assert "minimal upper body rotation" in flat

    def test_none_scores_empty_output(self, insights):
        scores = {
            "pressure_management": None,
            "turn_symmetry": None,
            "rotary_stability": None,
            "edge_consistency": None,
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
        }
        sections = insights.interpret_fundamentals(scores)
        assert sections == []

    def test_low_rhythm_inconsistent_feedback(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.2,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.5,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.8,
            "avg_turns_per_min": 15.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        headings = [h for h, _ in sections]
        assert "Turn Rhythm" in headings
        flat = "\n".join(b for _, bs in sections for b in bs)
        assert "inconsistent timing" in flat

    def test_high_rhythm_steady_feedback(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.85,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.5,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.15,
            "avg_turns_per_min": 25.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        flat = "\n".join(b for _, bs in sections for b in bs)
        assert "steady turn rhythm" in flat

    def test_metadata_accepted_no_error(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.6,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.5,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.4,
            "avg_turns_per_min": 20.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(
            scores, metadata={"height_cm": 157, "weight_kg": 63}
        )
        assert len(sections) > 0

    def test_value_lines_present(self, insights):
        scores = {
            "pressure_management": 0.5,
            "turn_symmetry": 0.8,
            "rotary_stability": 0.5,
            "edge_consistency": 0.5,
            "turn_shape_consistency": 0.5,
            "turn_rhythm": 0.6,
            "turn_efficiency": 0.9,
            "rotary_ratio_raw": 0.5,
            "speed_loss_avg": 0.1,
            "g_force_avg": 0.5,
            "radius_cv_raw": 0.4,
            "duration_cv_raw": 0.4,
            "avg_turns_per_min": 20.0,
            "normalized_turn_radius": 6.1,
            "pressure_ratio": 0.8,
            "torso_rotation_ratio": 0.5,
            "left_turns": 50,
            "right_turns": 50,
        }
        sections = insights.interpret_fundamentals(scores)
        for heading, bullets in sections:
            bracket_lines = [b for b in bullets if b.startswith("[")]
            assert len(bracket_lines) >= 1, f"{heading} missing value line"


# ---------------------------------------------------------------------------
# clean_insights (report pipeline)
# ---------------------------------------------------------------------------


class TestCleanInsights:
    def test_removes_headers_empty_and_brackets(self):
        raw = [
            "Turns analyzed: 556",
            "",
            "Fundamental Analysis",
            "",
            "Fore/Aft Balance",
            "  You maintain moderate fore/aft pressure through turns.",
            "  [pressure management: 0.52, avg speed loss: 0.0%]",
            "Edging Control",
            "You create consistent edge-driven turns with smooth engagement.",
            "[edge consistency: 0.88]",
        ]
        out = clean_insights(raw)
        assert "Turns analyzed" not in " ".join(out)
        assert "Fundamental Analysis" not in out
        assert "Fore/Aft Balance" not in out
        assert "Edging Control" not in out
        assert not any("[" in line for line in out)
        assert any("moderate fore/aft pressure" in line for line in out)
        assert any("consistent edge-driven" in line for line in out)

    def test_no_turns_message_preserved(self):
        out = clean_insights(["No turns detected in this session."])
        assert out == ["No turns detected in this session."]


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_has_turn_count_header(self, insights):
        df = _make_turn_df()
        result = insights.summarize_session({"total_turns": 50}, df=df)
        assert result[0] == "Turns analyzed: 50"

    def test_has_fundamental_analysis_header(self, insights):
        df = _make_turn_df()
        result = insights.summarize_session({"total_turns": 50}, df=df)
        assert "Fundamental Analysis" in result

    def test_contains_all_six_headings(self, insights):
        df = _make_turn_df()
        result = insights.summarize_session({"total_turns": 50}, df=df)
        flat = _flat(result)
        assert "Fore/Aft Balance" in flat
        assert "Foot-to-Foot Balance" in flat
        assert "Rotary Control" in flat
        assert "Edging Control" in flat
        assert "Pressure Control" in flat
        assert "Turn Rhythm" in flat

    def test_sections_have_value_lines(self, insights):
        df = _make_turn_df()
        result = insights.summarize_session({"total_turns": 50}, df=df)
        bracket_lines = [l for l in result if l.strip().startswith("[")]
        assert len(bracket_lines) >= 6


# ---------------------------------------------------------------------------
# session_report integration
# ---------------------------------------------------------------------------

class TestSessionReport:
    def test_calls_analyzer_and_summarizes(self, insights):
        df = _make_turn_df()
        mock_analyzer = MagicMock()
        mock_analyzer.load_turns.return_value = df
        mock_analyzer.session_metrics.return_value = {
            "session_id": "sess_X",
            "total_turns": 50,
        }

        result = insights.session_report(mock_analyzer, "sess_X")

        mock_analyzer.load_turns.assert_called_once_with(["sess_X"])
        mock_analyzer.session_metrics.assert_called_once_with("sess_X")
        flat = _flat(result)
        assert "Turns analyzed: 50" in flat
        assert "Fundamental Analysis" in flat

    def test_metadata_passed_through(self, insights):
        df = _make_turn_df(
            pelvis_estimated_turn_radius=np.full(50, 10.0),
        )
        mock_analyzer = MagicMock()
        mock_analyzer.load_turns.return_value = df
        mock_analyzer.session_metrics.return_value = {
            "session_id": "s",
            "total_turns": 50,
        }
        meta = {"ski": {"length_cm": 164}, "skier": {"height_cm": 170}}
        result = insights.session_report(mock_analyzer, "s", metadata=meta)
        assert len(result) > 3

    def test_no_metadata_still_works(self, insights):
        df = _make_turn_df()
        mock_analyzer = MagicMock()
        mock_analyzer.load_turns.return_value = df
        mock_analyzer.session_metrics.return_value = {
            "session_id": "s",
            "total_turns": 50,
        }
        result = insights.session_report(mock_analyzer, "s")
        flat = _flat(result)
        assert "Turns analyzed: 50" in flat
        assert "Fundamental Analysis" in flat
