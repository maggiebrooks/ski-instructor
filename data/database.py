"""SQLite persistence for ski session, run, and turn data.

Usage::

    db = init_db("data/ski.db")
    insert_session(db, session_dict)
    insert_run(db, run_dict)
    insert_turn(db, turn_dict)
    db.close()
"""

import sqlite3


def init_db(db_path):
    """Open (or create) the SQLite database and ensure all tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id          TEXT PRIMARY KEY,
            date                TEXT,
            duration_seconds    REAL,
            total_vertical      REAL,
            num_runs            INTEGER,
            total_turns         INTEGER,
            max_speed_kmh       REAL,
            schema_version      TEXT  -- TODO: split schema_version and processing_version when analytics diverge from DB schema
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id              TEXT PRIMARY KEY,
            session_id          TEXT,
            run_index           INTEGER,
            duration_seconds    REAL,
            vertical            REAL,
            avg_speed           REAL,
            max_speed_kmh       REAL,
            num_turns           INTEGER,
            turns_left          INTEGER,
            turns_right         INTEGER,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS turns (
            turn_id                             TEXT PRIMARY KEY,
            run_id                              TEXT,
            turn_index                          INTEGER,
            sensor_source                       TEXT DEFAULT 'pelvis_phone',
            direction                           TEXT,
            duration_seconds                    REAL,
            speed_at_apex                       REAL,
            speed_loss_ratio                    REAL,
            pelvis_integrated_turn_angle        REAL,
            pelvis_peak_angular_velocity        REAL,
            pelvis_max_roll_angle               REAL,
            pelvis_estimated_turn_radius        REAL,
            pelvis_peak_g_force                 REAL,
            pelvis_symmetry                     REAL,
            pelvis_edge_build_progressiveness   REAL,
            pelvis_radius_stability             REAL,
            FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
    """)
    conn.commit()
    return conn


def insert_session(conn, d):
    """Insert or replace a session row from a summary dict."""
    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (session_id, date, duration_seconds, total_vertical,
            num_runs, total_turns, max_speed_kmh, schema_version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["session_id"],
            d.get("date"),
            d.get("session_duration_s"),
            d.get("total_vertical_m"),
            d.get("num_runs"),
            d.get("total_turns"),
            d.get("max_speed_kmh"),
            d.get("schema_version"),
        ),
    )
    conn.commit()


def insert_run(conn, d):
    """Insert or replace a run row."""
    conn.execute(
        """INSERT OR REPLACE INTO runs
           (run_id, session_id, run_index, duration_seconds, vertical,
            avg_speed, max_speed_kmh, num_turns, turns_left, turns_right)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["run_id"],
            d["session_id"],
            d.get("run_index"),
            d.get("duration_s"),
            d.get("vertical_drop_m"),
            d.get("avg_speed_ms"),
            d.get("max_speed_kmh"),
            d.get("num_turns"),
            d.get("turns_left"),
            d.get("turns_right"),
        ),
    )
    conn.commit()


def insert_turn(conn, d):
    """Insert or replace a turn row."""
    conn.execute(
        """INSERT OR REPLACE INTO turns
           (turn_id, run_id, turn_index, sensor_source, direction,
            duration_seconds, speed_at_apex, speed_loss_ratio,
            pelvis_integrated_turn_angle, pelvis_peak_angular_velocity,
            pelvis_max_roll_angle, pelvis_estimated_turn_radius,
            pelvis_peak_g_force, pelvis_symmetry,
            pelvis_edge_build_progressiveness, pelvis_radius_stability)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["turn_id"],
            d["run_id"],
            d.get("turn_index"),
            d.get("sensor_source", "pelvis_phone"),
            d.get("direction"),
            d.get("duration_s"),
            d.get("speed_at_apex_kmh"),
            d.get("speed_loss_ratio"),
            d.get("pelvis_turn_angle_deg"),
            d.get("pelvis_peak_rotation_rate"),
            d.get("pelvis_max_roll_angle_deg"),
            d.get("pelvis_turn_radius_m"),
            d.get("pelvis_peak_g_force"),
            d.get("pelvis_symmetry"),
            d.get("pelvis_edge_build_progressiveness"),
            d.get("pelvis_radius_stability_cov"),
        ),
    )
    conn.commit()
