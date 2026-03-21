"""Unit tests for the TurnAnalyzer read-only analytics layer.

Run with:  python -m pytest tests/test_turn_analyzer.py -v
"""

import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import init_db, insert_session, insert_run, insert_turn
from ski.analysis.turn_analyzer import TurnAnalyzer


# ---------------------------------------------------------------------------
# Fixture: temporary SQLite DB with known data
# ---------------------------------------------------------------------------

@pytest.fixture()
def analyzer_with_data():
    """Create a temp DB with two sessions, insert known turns, return analyzer."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = init_db(db_path)

    insert_session(conn, {
        "session_id": "sess_A",
        "date": "2026-02-22",
        "session_duration_s": 3600,
        "total_vertical_m": 1500,
        "num_runs": 2,
        "total_turns": 4,
        "max_speed_kmh": 55.0,
        "schema_version": "2.0.0",
    })
    insert_session(conn, {
        "session_id": "sess_B",
        "date": "2026-02-24",
        "session_duration_s": 7200,
        "total_vertical_m": 3000,
        "num_runs": 1,
        "total_turns": 2,
        "max_speed_kmh": 60.0,
        "schema_version": "2.0.0",
    })

    insert_run(conn, {
        "run_id": "sess_A_run_1",
        "session_id": "sess_A",
        "run_index": 1,
        "duration_s": 120,
        "vertical_drop_m": 400,
        "avg_speed_ms": 10.0,
        "max_speed_kmh": 50.0,
        "num_turns": 3,
        "turns_left": 2,
        "turns_right": 1,
    })
    insert_run(conn, {
        "run_id": "sess_A_run_2",
        "session_id": "sess_A",
        "run_index": 2,
        "duration_s": 60,
        "vertical_drop_m": 200,
        "avg_speed_ms": 8.0,
        "max_speed_kmh": 40.0,
        "num_turns": 1,
        "turns_left": 0,
        "turns_right": 1,
    })
    insert_run(conn, {
        "run_id": "sess_B_run_1",
        "session_id": "sess_B",
        "run_index": 1,
        "duration_s": 180,
        "vertical_drop_m": 600,
        "avg_speed_ms": 12.0,
        "max_speed_kmh": 60.0,
        "num_turns": 2,
        "turns_left": 1,
        "turns_right": 1,
    })

    turns = [
        {"turn_id": "sess_A_run_1_turn_1", "run_id": "sess_A_run_1",
         "turn_index": 1, "direction": "left", "duration_s": 2.0,
         "speed_at_apex_kmh": 30.0, "speed_loss_ratio": 0.1,
         "pelvis_turn_angle_deg": -25.0, "pelvis_peak_rotation_rate": 1.5,
         "pelvis_max_roll_angle_deg": 40.0, "pelvis_turn_radius_m": 10.0,
         "pelvis_peak_g_force": 0.9, "pelvis_symmetry": 0.8,
         "pelvis_edge_build_progressiveness": 50.0,
         "pelvis_radius_stability_cov": 0.5},

        {"turn_id": "sess_A_run_1_turn_2", "run_id": "sess_A_run_1",
         "turn_index": 2, "direction": "right", "duration_s": 3.0,
         "speed_at_apex_kmh": 40.0, "speed_loss_ratio": 0.05,
         "pelvis_turn_angle_deg": 30.0, "pelvis_peak_rotation_rate": 2.0,
         "pelvis_max_roll_angle_deg": 50.0, "pelvis_turn_radius_m": 12.0,
         "pelvis_peak_g_force": 1.1, "pelvis_symmetry": 0.7,
         "pelvis_edge_build_progressiveness": 60.0,
         "pelvis_radius_stability_cov": 0.4},

        {"turn_id": "sess_A_run_1_turn_3", "run_id": "sess_A_run_1",
         "turn_index": 3, "direction": "left", "duration_s": 2.5,
         "speed_at_apex_kmh": 35.0, "speed_loss_ratio": 0.08,
         "pelvis_turn_angle_deg": -20.0, "pelvis_peak_rotation_rate": 1.8,
         "pelvis_max_roll_angle_deg": 45.0, "pelvis_turn_radius_m": 8.0,
         "pelvis_peak_g_force": 1.0, "pelvis_symmetry": 0.9,
         "pelvis_edge_build_progressiveness": 55.0,
         "pelvis_radius_stability_cov": 0.6},

        {"turn_id": "sess_A_run_2_turn_1", "run_id": "sess_A_run_2",
         "turn_index": 1, "direction": "right", "duration_s": 4.0,
         "speed_at_apex_kmh": 25.0, "speed_loss_ratio": 0.15,
         "pelvis_turn_angle_deg": 35.0, "pelvis_peak_rotation_rate": 1.2,
         "pelvis_max_roll_angle_deg": 35.0, "pelvis_turn_radius_m": 14.0,
         "pelvis_peak_g_force": 0.8, "pelvis_symmetry": 0.6,
         "pelvis_edge_build_progressiveness": 40.0,
         "pelvis_radius_stability_cov": 0.7},

        {"turn_id": "sess_B_run_1_turn_1", "run_id": "sess_B_run_1",
         "turn_index": 1, "direction": "left", "duration_s": 3.0,
         "speed_at_apex_kmh": 50.0, "speed_loss_ratio": 0.02,
         "pelvis_turn_angle_deg": -40.0, "pelvis_peak_rotation_rate": 2.5,
         "pelvis_max_roll_angle_deg": 60.0, "pelvis_turn_radius_m": 6.0,
         "pelvis_peak_g_force": 1.3, "pelvis_symmetry": 0.95,
         "pelvis_edge_build_progressiveness": 80.0,
         "pelvis_radius_stability_cov": 0.3},

        {"turn_id": "sess_B_run_1_turn_2", "run_id": "sess_B_run_1",
         "turn_index": 2, "direction": "right", "duration_s": 2.5,
         "speed_at_apex_kmh": 45.0, "speed_loss_ratio": 0.04,
         "pelvis_turn_angle_deg": 35.0, "pelvis_peak_rotation_rate": 2.2,
         "pelvis_max_roll_angle_deg": 55.0, "pelvis_turn_radius_m": 8.0,
         "pelvis_peak_g_force": 1.2, "pelvis_symmetry": 0.85,
         "pelvis_edge_build_progressiveness": 75.0,
         "pelvis_radius_stability_cov": 0.35},
    ]
    for t in turns:
        insert_turn(conn, t)

    conn.close()

    yield TurnAnalyzer(db_path), db_path

    os.unlink(db_path)


@pytest.fixture()
def empty_analyzer():
    """Analyzer pointing at a DB with sessions/runs but zero turns."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = init_db(db_path)
    insert_session(conn, {
        "session_id": "empty_sess",
        "date": "2026-03-01",
        "session_duration_s": 100,
        "total_vertical_m": 0,
        "num_runs": 0,
        "total_turns": 0,
        "max_speed_kmh": 0,
        "schema_version": "2.0.0",
    })
    conn.close()

    yield TurnAnalyzer(db_path), db_path

    os.unlink(db_path)


# ---------------------------------------------------------------------------
# TestLoadTurns
# ---------------------------------------------------------------------------

class TestLoadTurns:
    def test_returns_all_turns(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.load_turns()
        assert len(df) == 6

    def test_returns_correct_columns(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.load_turns()
        expected = {
            "session_id", "run_id", "direction", "duration_seconds",
            "speed_at_apex", "speed_loss_ratio",
            "pelvis_integrated_turn_angle", "pelvis_peak_angular_velocity",
            "pelvis_max_roll_angle", "pelvis_estimated_turn_radius",
            "pelvis_peak_g_force", "pelvis_symmetry",
            "pelvis_edge_build_progressiveness", "pelvis_radius_stability",
        }
        assert set(df.columns) == expected

    def test_filter_single_session(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.load_turns(session_ids=["sess_A"])
        assert len(df) == 4
        assert (df["session_id"] == "sess_A").all()

    def test_filter_multiple_sessions(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.load_turns(session_ids=["sess_A", "sess_B"])
        assert len(df) == 6

    def test_filter_nonexistent_session(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.load_turns(session_ids=["no_such_session"])
        assert len(df) == 0

    def test_empty_db_returns_empty_dataframe(self, empty_analyzer):
        analyzer, _ = empty_analyzer
        df = analyzer.load_turns(session_ids=["empty_sess"])
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# TestSessionMetrics
# ---------------------------------------------------------------------------

class TestSessionMetrics:
    def test_metrics_keys(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        expected_keys = {
            "session_id", "total_turns", "avg_turn_radius", "radius_std",
            "radius_cv", "avg_peak_ang_vel", "avg_speed_at_apex", "avg_g_force",
            "avg_symmetry", "left_turns", "right_turns", "turn_balance",
        }
        assert set(m.keys()) == expected_keys

    def test_total_turns(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        assert m["total_turns"] == 4

    def test_left_right_counts(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        assert m["left_turns"] == 2
        assert m["right_turns"] == 2

    def test_avg_turn_radius(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        expected = (10.0 + 12.0 + 8.0 + 14.0) / 4
        assert m["avg_turn_radius"] == pytest.approx(expected, abs=0.01)

    def test_avg_speed_at_apex(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        expected = (30.0 + 40.0 + 35.0 + 25.0) / 4
        assert m["avg_speed_at_apex"] == pytest.approx(expected, abs=0.01)

    def test_session_id_in_result(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_B")
        assert m["session_id"] == "sess_B"

    def test_radius_cv(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        expected_cv = m["radius_std"] / m["avg_turn_radius"]
        assert m["radius_cv"] == pytest.approx(round(expected_cv, 2), abs=0.01)

    def test_turn_balance_perfect(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        m = analyzer.session_metrics("sess_A")
        assert m["turn_balance"] == 0.0

    def test_empty_session_returns_none_metrics(self, empty_analyzer):
        analyzer, _ = empty_analyzer
        m = analyzer.session_metrics("empty_sess")
        assert m["total_turns"] == 0
        assert m["avg_turn_radius"] is None
        assert m["avg_speed_at_apex"] is None
        assert m["radius_cv"] is None
        assert m["turn_balance"] is None
        assert m["left_turns"] == 0
        assert m["right_turns"] == 0


# ---------------------------------------------------------------------------
# TestCompareSessions
# ---------------------------------------------------------------------------

class TestCompareSessions:
    def test_returns_dataframe(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.compare_sessions(["sess_A", "sess_B"])
        assert isinstance(df, pd.DataFrame)

    def test_one_row_per_session(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.compare_sessions(["sess_A", "sess_B"])
        assert len(df) == 2

    def test_correct_turn_counts(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.compare_sessions(["sess_A", "sess_B"])
        df = df.set_index("session_id")
        assert df.loc["sess_A", "total_turns"] == 4
        assert df.loc["sess_B", "total_turns"] == 2

    def test_metrics_match_session_metrics(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        single = analyzer.session_metrics("sess_B")
        compared = analyzer.compare_sessions(["sess_A", "sess_B"])
        row = compared.set_index("session_id").loc["sess_B"]
        assert row["avg_turn_radius"] == pytest.approx(single["avg_turn_radius"])
        assert row["avg_speed_at_apex"] == pytest.approx(single["avg_speed_at_apex"])
        assert row["total_turns"] == single["total_turns"]
        assert row["radius_cv"] == pytest.approx(single["radius_cv"])
        assert row["turn_balance"] == pytest.approx(single["turn_balance"])

    def test_empty_session_ids_returns_empty(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.compare_sessions(["no_such_session"])
        assert len(df) == 0


# ---------------------------------------------------------------------------
# TestRunMetrics
# ---------------------------------------------------------------------------

class TestRunMetrics:
    def test_returns_dataframe(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.run_metrics("sess_A")
        assert isinstance(df, pd.DataFrame)

    def test_one_row_per_run(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.run_metrics("sess_A")
        assert len(df) == 2

    def test_correct_turn_counts(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.run_metrics("sess_A").set_index("run_id")
        assert df.loc["sess_A_run_1", "turn_count"] == 3
        assert df.loc["sess_A_run_2", "turn_count"] == 1

    def test_avg_turn_radius(self, analyzer_with_data):
        analyzer, _ = analyzer_with_data
        df = analyzer.run_metrics("sess_A").set_index("run_id")
        expected = (10.0 + 12.0 + 8.0) / 3
        assert df.loc["sess_A_run_1", "avg_turn_radius"] == pytest.approx(expected, abs=0.01)

    def test_empty_session_returns_empty(self, empty_analyzer):
        analyzer, _ = empty_analyzer
        df = analyzer.run_metrics("empty_sess")
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)
