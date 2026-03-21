"""Pydantic schemas for data contract enforcement.

All schemas enforce no NaNs, reasonable value ranges, and explicit units.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Validation result (shared by input/output validators)
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Result of a validation pass."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------------------------------------------------------------------------
# Raw sensor data (pre-ingestion)
# ---------------------------------------------------------------------------


class RawSensorSchema(BaseModel):
    """Single row of raw sensor data from Sensor Logger CSV.

    Enforces no NaNs and reasonable physical bounds.
    """

    timestamp: float | int = Field(..., description="Time in seconds or nanoseconds")
    accelerometer_x: float = Field(..., ge=-50, le=50, description="m/s²")
    accelerometer_y: float = Field(..., ge=-50, le=50, description="m/s²")
    accelerometer_z: float = Field(..., ge=-50, le=50, description="m/s²")
    gyroscope_x: float = Field(..., ge=-50, le=50, description="rad/s")
    gyroscope_y: float = Field(..., ge=-50, le=50, description="rad/s")
    gyroscope_z: float = Field(..., ge=-50, le=50, description="rad/s")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    altitude: float | None = Field(None, ge=-500, le=10000)

    @field_validator("accelerometer_x", "accelerometer_y", "accelerometer_z")
    @classmethod
    def no_nan_accel(cls, v: float) -> float:
        if v != v:  # NaN check
            raise ValueError("Accelerometer values cannot be NaN")
        return v

    @field_validator("gyroscope_x", "gyroscope_y", "gyroscope_z")
    @classmethod
    def no_nan_gyro(cls, v: float) -> float:
        if v != v:
            raise ValueError("Gyroscope values cannot be NaN")
        return v


# ---------------------------------------------------------------------------
# Processed row (post-preprocessing)
# ---------------------------------------------------------------------------


class ProcessedRowSchema(BaseModel):
    """Single row of preprocessed session data."""

    timestamp: float = Field(..., ge=0)
    accel_magnitude: float = Field(..., ge=0, le=50)
    gyro_magnitude: float = Field(..., ge=0, le=50)
    velocity: float | None = Field(None, ge=0, le=150)
    roll: float | None = Field(None, ge=-3.15, le=3.15)
    pitch: float | None = Field(None, ge=-3.15, le=3.15)
    yaw: float | None = Field(None, ge=-3.15, le=3.15)


# ---------------------------------------------------------------------------
# Turn (per-turn metrics from DB)
# ---------------------------------------------------------------------------


class TurnSchema(BaseModel):
    """Single turn record from the pipeline."""

    session_id: str
    run_id: str
    turn_id: str
    turn_direction: str = Field(..., pattern="^(left|right)$")
    turn_radius: float | None = Field(None, gt=0, le=500)
    edge_angle: float | None = Field(None, ge=0, le=90)
    speed: float = Field(..., ge=0, le=150)
    timestamp_start: float | None = None
    timestamp_end: float | None = None

    @field_validator("turn_radius")
    @classmethod
    def radius_no_nan(cls, v: float | None) -> float | None:
        if v is not None and v != v:
            raise ValueError("turn_radius cannot be NaN")
        return v

    @field_validator("edge_angle")
    @classmethod
    def edge_no_nan(cls, v: float | None) -> float | None:
        if v is not None and v != v:
            raise ValueError("edge_angle cannot be NaN")
        return v


# ---------------------------------------------------------------------------
# Session summary (report.json summary block)
# ---------------------------------------------------------------------------


class SessionSummarySchema(BaseModel):
    """Session-level summary from report."""

    runs: int | None = Field(None, ge=0)
    turns: int | None = Field(None, ge=0)
    vertical_m: float | None = Field(None, ge=0, le=10000)
    max_speed_kmh: float | None = Field(None, ge=0, le=200)
    duration_s: float | None = Field(None, ge=0, le=86400)
    duration_minutes: float | None = Field(None, ge=0, le=1440)


# ---------------------------------------------------------------------------
# Report (full API response)
# ---------------------------------------------------------------------------


class ReportSchema(BaseModel):
    """Full report structure returned by the API."""

    session_id: str
    status: str = Field(..., pattern="^(complete|processing|error)$")
    summary: SessionSummarySchema | dict[str, Any] | None = None
    scores: dict[str, float | None] = Field(default_factory=dict)
    normalized_metrics: dict[str, float | None] = Field(default_factory=dict)
    insights: list[str] = Field(default_factory=list)
    metric_confidence: dict[str, float] = Field(default_factory=dict)
    data_quality: dict[str, float] = Field(default_factory=dict)
    data_quality_flags: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}
