"""Post-pipeline validation of session outputs.

Validates that processed files exist and turn metrics fall in realistic ranges.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import sqlite3

from backend.config import DATA_DIR
from backend.contracts.schemas import ValidationResult
from backend.storage import BUCKETS

logger = logging.getLogger(__name__)

DB_PATH = str((DATA_DIR / "ski.db").resolve())


def validate_session_outputs(session_id: str) -> ValidationResult:
    """Validate pipeline outputs for a completed session.

    Parameters
    ----------
    session_id : str
        Session identifier.

    Returns
    -------
    ValidationResult
        valid=True if all checks pass.
        Raises ValueError if invalid (fail hard).
    """
    errors: list[str] = []
    warnings: list[str] = []

    session_dir = BUCKETS["processed"] / session_id
    if not session_dir.exists():
        errors.append(f"Session directory does not exist: {session_dir}")
        _fail(errors, warnings, session_id)

    safe_name = session_id.replace(" ", "_").replace("/", "_")

    # --- 1. Expected files exist ---
    processed_csv = session_dir / f"{safe_name}_processed.csv"
    report_json = session_dir / "report.json"

    if not processed_csv.exists():
        errors.append(f"Missing processed CSV: {processed_csv.name}")
    if not report_json.exists():
        errors.append(f"Missing report.json")

    if errors:
        _fail(errors, warnings, session_id)

    # --- 2. Report structure ---
    try:
        with open(report_json) as f:
            report = json.load(f)
    except Exception as e:
        errors.append(f"Invalid report.json: {e}")
        _fail(errors, warnings, session_id)

    if report.get("status") != "complete":
        warnings.append(f"Report status is '{report.get('status')}', not 'complete'")

    # --- 3. Turn metrics from DB (if turns exist) ---
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT t.turn_id, t.run_id, t.direction, t.pelvis_estimated_turn_radius,
                   t.pelvis_max_roll_angle, t.speed_at_apex
            FROM turns t
            JOIN runs r ON t.run_id = r.run_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        turn_id = row["turn_id"]
        direction = row["direction"]
        radius = row["pelvis_estimated_turn_radius"]
        edge_deg = row["pelvis_max_roll_angle"]
        speed = row["speed_at_apex"]

        if radius is not None:
            if radius <= 0:
                errors.append(f"Turn {turn_id}: turn_radius must be > 0, got {radius}")
            elif radius > 500:
                warnings.append(f"Turn {turn_id}: turn_radius {radius:.0f}m is unusually large")

        if edge_deg is not None:
            if edge_deg < 0 or edge_deg > 3600:
                errors.append(
                    f"Turn {turn_id}: pelvis_max_roll_angle must be 0-3600 deg, got {edge_deg}"
                )
            elif edge_deg > 90:
                warnings.append(
                    f"Turn {turn_id}: pelvis_max_roll_angle {edge_deg:.1f} deg unusually high (possible unit mismatch)"
                )

        if speed is not None and (speed < 0 or speed > 200):
            errors.append(f"Turn {turn_id}: speed_at_apex must be 0-200 km/h, got {speed}")

        if radius is not None and radius != radius:  # NaN
            errors.append(f"Turn {turn_id}: turn_radius is NaN")
        if edge_deg is not None and edge_deg != edge_deg:
            errors.append(f"Turn {turn_id}: edge_angle is NaN")

    # --- 4. Summary consistency ---
    summary = report.get("summary") or {}
    db_turns = len(rows)
    report_turns = summary.get("turns")
    if report_turns is not None and db_turns != report_turns:
        warnings.append(
            f"Turn count mismatch: DB has {db_turns}, report has {report_turns}"
        )

    if errors:
        _fail(errors, warnings, session_id)

    quality_score = 1.0 - 0.05 * len(warnings)
    quality_score = max(0.0, min(1.0, quality_score))

    result = ValidationResult(
        valid=True,
        errors=[],
        warnings=warnings,
        quality_score=quality_score,
    )

    if warnings:
        logger.warning(
            "output_validation_warnings",
            extra={"session_id": session_id, "warnings": warnings},
        )

    logger.info(
        "output_validation_passed",
        extra={"session_id": session_id, "quality_score": quality_score},
    )

    return result


def _fail(errors: list[str], warnings: list[str], session_id: str) -> None:
    """Raise ValueError with validation failure details."""
    msg = f"Output validation failed for {session_id}: " + "; ".join(errors)
    logger.error(
        "output_validation_failed",
        extra={"session_id": session_id, "errors": errors, "warnings": warnings},
    )
    raise ValueError(msg)
