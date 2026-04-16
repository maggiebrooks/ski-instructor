"""RQ worker: runs the ski analytics pipeline for an uploaded session."""

import io
import json
import logging
from pathlib import Path

from backend.config import DATA_DIR, LOGS_DIR, PLOTS_DIR, PROCESSED_DIR, RAW_DIR
from backend.models import update_job
from backend.storage import get_path, write_bytes

_LOG_DIR = LOGS_DIR

_handler = logging.FileHandler(_LOG_DIR / "worker.log")
_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_handler)

DB_PATH = str((DATA_DIR / "ski.db").resolve())

SKIP_PREFIXES = ("__MACOSX", ".")

# Max coaching sentences in report (after clean_insights); optional frame line added below.
TOP_COACHING_INSIGHTS_N = 5
_COACHING_FRAME = "For your next run, focus on the following:"
_NO_TURNS_INSIGHT = "No turns detected in this session."


def _resolve_raw_path(session_dir: Path) -> Path:
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


def run_pipeline(session_id: str) -> dict:
    """Execute the full pipeline + analytics for one uploaded session.

    Called by the RQ worker process.  Writes report.json to the
    processed artifacts directory for this session.
    """
    try:
        from ski.processing.session_processor import SessionProcessor
        from ski.analysis.turn_analyzer import TurnAnalyzer
        from ski.analysis.turn_insights import (
            TurnInsights,
            clean_insights,
            _generate_actionable_top_insight,
        )
        from ski.analysis.turn_signature import plot_session_signature

        session_dir = RAW_DIR / session_id
        if not session_dir.is_dir():
            # Upload and worker must share the same filesystem. Redis is global;
            # disk is not — if Railway (or any host) runs >1 replica, the HTTP
            # upload hits instance A's disk while the RQ worker on instance B
            # looks here and finds nothing.
            err = (
                f"Raw session directory missing: {session_dir} (RAW_DIR={RAW_DIR}). "
                "If uploads succeed but jobs fail, set this service to 1 replica "
                "(Railway: Settings → Scaling), or use shared/object storage for raw files."
            )
            logger.error(err)
            raise RuntimeError(err) from None

        raw_path = _resolve_raw_path(session_dir)

        # --- 1. Pre-pipeline validation (fail early if invalid) ---
        from backend.validation.input_validator import validate_raw_session

        update_job(session_id, "parsing_sensor_data")
        logger.info("Stage: parsing_sensor_data for %s", session_id)
        validation = validate_raw_session(raw_path)
        logger.info(
            "Input validation passed for %s (quality=%.2f)",
            session_id,
            validation.quality_score,
        )

        processed_dir = get_path(session_id, "processed")
        plots_dir = get_path(session_id, "plots")

        update_job(session_id, "running_pipeline")
        logger.info("Stage: running_pipeline for %s", session_id)

        # --- 2. Run pipeline (unchanged) ---
        processor = SessionProcessor(db_path=DB_PATH, processing_version="2.0.0")
        summary = processor.process(
            session_id=session_id,
            raw_path=raw_path,
            processed_dir=processed_dir,
            output_dir=plots_dir,
        )

        update_job(session_id, "generating_report")
        logger.info("Stage: generating_report for %s", session_id)
        analyzer = TurnAnalyzer(DB_PATH)
        insights_engine = TurnInsights()
        report_lines = insights_engine.session_report(analyzer, session_id)

        df = analyzer.load_turns([session_id])

        # --- Data quality & confidence (additive layer) ---
        from backend.metrics.confidence import compute_data_quality_flags
        import pandas as pd

        safe_name = session_id.replace(" ", "_").replace("/", "_")
        processed_csv = processed_dir / f"{safe_name}_processed.csv"
        df_processed = pd.read_csv(processed_csv) if processed_csv.exists() else pd.DataFrame()
        from ski.analysis.data_quality import evaluate_data_quality
        from ski.analysis.confidence import compute_per_turn_confidence

        data_quality = evaluate_data_quality(df_processed)

        # --- Filter turns by confidence (orchestration layer) ---
        CONFIDENCE_THRESHOLD = 0.7
        MIN_TURNS_REQUIRED = 5

        total_turn_count = len(df)
        if total_turn_count > 0:
            df = df.copy()
            df["confidence"] = df.apply(
                lambda row: compute_per_turn_confidence(row.to_dict(), data_quality),
                axis=1,
            )
            filtered_df = df[df["confidence"] >= CONFIDENCE_THRESHOLD]
            filtered_turn_count = len(filtered_df)
        else:
            filtered_df = df
            filtered_turn_count = 0

        low_confidence_warning = filtered_turn_count < MIN_TURNS_REQUIRED

        if filtered_turn_count == 0:
            score_confidence = "low"
        elif filtered_turn_count < MIN_TURNS_REQUIRED:
            score_confidence = "medium"
        else:
            score_confidence = "high"

        scores = TurnInsights.compute_movement_scores(filtered_df)

        metadata = {
            "scores": scores,
            "summary": summary,
            "total_turns": summary.get("total_turns"),
        }
        from backend.metrics.confidence import compute_confidence

        metric_confidence = compute_confidence(df_processed, metadata)

        data_quality_flags = compute_data_quality_flags(
            data_quality,
            turn_count=summary.get("total_turns"),
            session_duration_s=summary.get("session_duration_s"),
        )

        logger.info("Data quality for %s: %s", session_id, data_quality)
        logger.info("Metric confidence for %s: %s", session_id, metric_confidence)
        logger.info("Data quality flags for %s: %s", session_id, data_quality_flags)

        update_job(session_id, "generating_plots")
        logger.info("Stage: generating_plots for %s", session_id)
        fig = plot_session_signature(analyzer, session_id, show=False)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        write_bytes(session_id, "plots", f"{session_id}_turn_signature.png", buf.getvalue())

        import matplotlib.pyplot as plt
        plt.close(fig)

        warnings = []
        if low_confidence_warning:
            warnings.append(
                f"Low confidence: only {filtered_turn_count} high-quality turns available"
            )

        cleaned_insights = clean_insights(report_lines)
        top_insights = cleaned_insights[:TOP_COACHING_INSIGHTS_N]
        if top_insights:
            only_no_turns = (
                len(top_insights) == 1 and top_insights[0].strip() == _NO_TURNS_INSIGHT
            )
            if not only_no_turns:
                top_insights.insert(0, _COACHING_FRAME)

        report = {
            "session_id": session_id,
            "status": "complete",
            "processing_version": "2.0.0",
            "summary": {
                "runs": summary.get("num_runs"),
                "turns": summary.get("total_turns"),
                "vertical_m": summary.get("total_vertical_m"),
                "max_speed_kmh": summary.get("max_speed_kmh"),
                "duration_s": summary.get("session_duration_s"),
            },
            "scores": {
                k: scores.get(k)
                for k in [
                    "rotary_stability",
                    "edge_consistency",
                    "pressure_management",
                    "turn_symmetry",
                    "turn_shape_consistency",
                    "turn_rhythm",
                    "turn_efficiency",
                ]
            },
            "normalized_metrics": {
                "pressure_ratio": scores.get("pressure_ratio"),
                "torso_rotation_ratio": scores.get("torso_rotation_ratio"),
                "normalized_turn_radius": scores.get("normalized_turn_radius"),
            },
            "insights": top_insights,
            "data_quality": data_quality,
            "metric_confidence": metric_confidence,
            "data_quality_flags": data_quality_flags,
            "confidence_threshold_used": CONFIDENCE_THRESHOLD,
            "total_turn_count": total_turn_count,
            "filtered_turn_count": filtered_turn_count,
            "low_confidence_warning": low_confidence_warning,
            "score_confidence": score_confidence,
        }
        report.setdefault("warnings", []).extend(warnings)
        # Single source of truth: deterministic map from movement scores (not stale report.json).
        report["top_insight"] = _generate_actionable_top_insight(scores)
        logger.info("top_insight for %s: %s", session_id, report["top_insight"][:120])

        write_bytes(
            session_id, "processed", "report.json",
            json.dumps(report, indent=2).encode(),
        )

        # --- Post-pipeline output validation ---
        from backend.validation.output_validator import validate_session_outputs

        validate_session_outputs(session_id)
        logger.info("Output validation passed for %s", session_id)

        update_job(session_id, "complete")
        logger.info("Stage: complete for %s", session_id)
        report_path = get_path(session_id, "processed", "report.json")
        logger.info("Pipeline complete for %s -> %s", session_id, report_path)
        return report

    except Exception as e:
        logger.exception("Pipeline failed for %s", session_id)
        update_job(session_id, "error", error=str(e))
        logger.info("Stage: error for %s", session_id)
        raise
