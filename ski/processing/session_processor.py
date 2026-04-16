"""Reusable orchestration class for the ski analytics pipeline.

Usage::

    processor = SessionProcessor(db_path="data/ski.db")
    summary = processor.process("Session_Name", Path("data/Session_Name"))
"""

import os
import re
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionProcessor:
    """Executes the full ski session pipeline programmatically.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    processing_version : str
        Algorithm/processing version string.  Stored in the DB
        ``schema_version`` column for now.
    """

    def __init__(self, db_path: str, processing_version: str = "2.0.0"):
        self.db_path = db_path
        self.processing_version = processing_version

    def process(
        self,
        session_id: str,
        raw_path: Path,
        processed_dir: Path | None = None,
        output_dir: Path | None = None,
    ) -> dict:
        """Execute the full pipeline for one session.

        Parameters
        ----------
        session_id : str
            Identifier for the session (used in filenames and DB keys).
        raw_path : Path
            Path to the raw Sensor Logger session folder.
        processed_dir : Path | None
            Where to write CSV/JSON artifacts.  Defaults to
            ``raw_path.parent / "processed"`` (co-located with raw data).
        output_dir : Path | None
            Where to write PNG visualisations.  Defaults to
            ``Path("output").resolve()`` (project-root-relative).

        Returns
        -------
        dict
            Session summary (same structure as JSON output).
        """
        from transformations.process_session import (
            load_session,
            preprocess,
            compute_row_features,
            segment_runs,
            detect_turns_by_run,
            compute_session_summary,
            plot_session,
        )
        from data.database import init_db, insert_session, insert_run, insert_turn

        if processed_dir is None:
            processed_dir = raw_path.parent / "processed"
        if output_dir is None:
            output_dir = Path("output").resolve()

        processed_dir = Path(processed_dir)
        output_dir = Path(output_dir)
        os.makedirs(processed_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        safe_name = session_id.replace(" ", "_").replace("/", "_")

        # ----- 1. Ingest -----
        logger.info("Loading session: %s", session_id)
        df = load_session(str(raw_path))
        logger.info("Loaded: %s rows x %d columns", f"{df.shape[0]:,}", df.shape[1])

        # ----- 2. Preprocess -----
        logger.info("Preprocessing …")
        df = preprocess(df)
        logger.info("After preprocessing: %s rows @ 20 Hz", f"{df.shape[0]:,}")

        # ----- 3. Row-level features -----
        logger.info("Computing features …")
        df = compute_row_features(df)

        # ----- 4. Segment runs -----
        logger.info("Segmenting runs …")
        df = segment_runs(df)
        n_runs = df.loc[df["activity"] == "skiing", "run_id"].nunique()
        ski_time = (df["activity"] == "skiing").sum() / 20
        lift_time = (df["activity"] == "lift").sum() / 20
        idle_time = (df["activity"] == "idle").sum() / 20
        logger.info(
            "%d ski runs | skiing %.1f min, lift %.1f min, idle %.1f min",
            n_runs, ski_time / 60, lift_time / 60, idle_time / 60,
        )

        # ----- 5. Turn detection -----
        logger.info("Detecting turns (skiing runs only) …")
        df, run_results = detect_turns_by_run(df)
        total_turns = sum(r["num_turns"] for r in run_results)
        logger.info("%d turns across %d runs", total_turns, len(run_results))

        for r in run_results:
            radius_str = (f"{r['avg_turn_radius_m']:.0f}m"
                          if r.get("avg_turn_radius_m") else "n/a")
            vert = r.get("vertical_drop_m")
            vert_str = f"{vert:5.1f}m" if vert is not None else "  n/a"
            logger.info(
                "  Run %2d: %3d turns, %6.1fs, vert %s, "
                "max %.1f km/h, avg radius %s, L/R %d/%d",
                r["run_id"], r["num_turns"], r["duration_s"],
                vert_str, r["max_speed_kmh"], radius_str,
                r.get("turns_left", 0), r.get("turns_right", 0),
            )

        # ----- 6. Save processed CSV -----
        csv_out = str(processed_dir / f"{safe_name}_processed.csv")
        df.to_csv(csv_out, index=False)
        logger.info("Saved CSV -> %s", csv_out)

        # ----- 7. Session summary -----
        logger.info("Computing session summary …")
        summary_path = str(processed_dir / f"{safe_name}_summary.json")
        summary = compute_session_summary(df, run_results,
                                          output_path=summary_path)
        logger.info(
            "Session: %ss, %d runs, %d turns, %sm vertical",
            summary["session_duration_s"], summary["num_runs"],
            summary["total_turns"], summary["total_vertical_m"],
        )

        # ----- 8. Visualisation -----
        logger.info("Generating plot …")
        plot_path = str(output_dir / f"{safe_name}_session.png")
        plot_session(df, plot_path, run_results=run_results)

        # ----- 9. Persist to SQLite -----
        logger.info("Writing to database -> %s", self.db_path)
        db = init_db(self.db_path)

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", session_id)
        if date_match:
            session_date = date_match.group(1)
        else:
            logger.warning("No date pattern found in session_id '%s'", session_id)
            session_date = None

        insert_session(db, {
            "session_id": session_id,
            "date": session_date,
            "session_duration_s": summary["session_duration_s"],
            "total_vertical_m": summary["total_vertical_m"],
            "num_runs": summary["num_runs"],
            "total_turns": summary["total_turns"],
            "max_speed_kmh": summary["max_speed_kmh"],
            "schema_version": self.processing_version,
        })

        for r in run_results:
            db_run_id = f"{session_id}_run_{r['run_id']}"
            insert_run(db, {
                "run_id": db_run_id,
                "session_id": session_id,
                "run_index": r["run_id"],
                "duration_s": r["duration_s"],
                "vertical_drop_m": r["vertical_drop_m"],
                "avg_speed_ms": r["avg_speed_ms"],
                "max_speed_kmh": r["max_speed_kmh"],
                "num_turns": r["num_turns"],
                "turns_left": r.get("turns_left"),
                "turns_right": r.get("turns_right"),
            })

            for t in r.get("per_turn", []):
                db_turn_id = f"{db_run_id}_turn_{t['turn_id']}"
                insert_turn(db, {
                    "turn_id": db_turn_id,
                    "run_id": db_run_id,
                    "turn_index": t["turn_id"],
                    "sensor_source": t["sensor_source"],
                    "direction": t["direction"],
                    "pelvis_turn_angle_deg": t["pelvis_turn_angle_deg"],
                    "pelvis_peak_rotation_rate": t["pelvis_peak_rotation_rate"],
                    "pelvis_max_roll_angle_deg": t["pelvis_max_roll_angle_deg"],
                    "speed_at_apex_kmh": t["speed_at_apex_kmh"],
                    "pelvis_turn_radius_m": t["pelvis_turn_radius_m"],
                    "pelvis_peak_g_force": t["pelvis_peak_g_force"],
                    "pelvis_symmetry": t["pelvis_symmetry"],
                    "duration_s": t["duration_s"],
                    "pelvis_edge_build_progressiveness":
                        t.get("pelvis_edge_build_progressiveness"),
                    "pelvis_radius_stability_cov":
                        t.get("pelvis_radius_stability_cov"),
                    "speed_loss_ratio": t.get("speed_loss_ratio"),
                })

        db.close()
        n_turns_db = sum(r["num_turns"] for r in run_results)
        logger.info("Inserted: 1 session, %d runs, %d turns",
                     len(run_results), n_turns_db)

        logger.info("Done: %s", session_id)
        return summary
