"""Metric definition registry with provenance metadata.

Each metric computed by the pipeline is catalogued here with its
equation, source, assumptions, and limitations.  This enables
programmatic inspection of metric provenance and powers the
confidence scoring system.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricDefinition:
    """Immutable description of a single pipeline metric."""

    name: str
    equation: str
    variables: dict[str, str]
    source: str
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    category: str = "physics"  # "physics" or "heuristic"

    def __post_init__(self):
        if self.category not in ("physics", "heuristic"):
            raise ValueError(
                f"category must be 'physics' or 'heuristic', got {self.category!r}"
            )


METRICS: dict[str, MetricDefinition] = {
    "speed": MetricDefinition(
        name="Speed",
        equation="v = v_GPS",
        variables={"v": "ground speed (m/s)", "v_GPS": "GPS-reported speed (m/s)"},
        source="GPS Doppler velocity measurement",
        assumptions=(
            "GPS receiver reports instantaneous ground speed",
            "Smartphone GPS operates at ~1 Hz; interpolated between fixes",
        ),
        limitations=(
            "Degraded under tree cover or poor satellite geometry",
            "Ground-plane projected; underestimates true slope-velocity",
        ),
        category="physics",
    ),
    "angular_velocity": MetricDefinition(
        name="Angular Velocity",
        equation="omega = gyro_z",
        variables={"omega": "yaw angular velocity (rad/s)", "gyro_z": "gyroscope z-axis (rad/s)"},
        source="Direct MEMS gyroscope measurement",
        assumptions=(
            "Phone z-axis approximates body yaw axis",
            "Gyroscope bias drift negligible over single turns",
        ),
        limitations=(
            "Phone movement in pocket misaligns axis",
            "Signal approaches noise floor below 0.1 rad/s",
        ),
        category="physics",
    ),
    "turn_radius": MetricDefinition(
        name="Turn Radius",
        equation="r = v / omega",
        variables={
            "r": "turn radius (m)",
            "v": "speed at apex (m/s)",
            "omega": "peak angular velocity (rad/s)",
        },
        source="Circular motion kinematics (v = omega * r)",
        assumptions=(
            "Instantaneous circular arc at turn apex",
            "Rigid body approximation",
            "Gyro yaw rate corresponds to ground-plane turning rate",
        ),
        limitations=(
            "Diverges when omega < 0.1 rad/s (guarded)",
            "Non-circular paths (skidded turns) violate assumption",
            "GPS-gyro timing mismatch (1 Hz vs 100 Hz)",
        ),
        category="physics",
    ),
    "centripetal_acceleration": MetricDefinition(
        name="Centripetal Acceleration",
        equation="a_c = v^2 / r = v * omega",
        variables={
            "a_c": "centripetal acceleration (m/s^2)",
            "v": "speed at apex (m/s)",
            "r": "turn radius (m)",
        },
        source="Newton's second law applied to circular motion",
        assumptions=(
            "Instantaneous circular motion at apex",
            "No lateral sliding (pure carving)",
        ),
        limitations=(
            "Inherits all turn radius limitations",
            "Unrealistic when radius is very small at high speed",
        ),
        category="physics",
    ),
    "pressure_ratio": MetricDefinition(
        name="Pressure Ratio",
        equation="pressure_ratio = g_measured / (v^2 / (r * 9.81))",
        variables={
            "g_measured": "peak acceleration / 9.807 (g)",
            "v": "speed at apex (m/s)",
            "r": "turn radius (m)",
        },
        source="Ratio of measured vs Newtonian centripetal acceleration",
        assumptions=(
            "Circular arc at apex",
            "Accelerometer measures centripetal loading after gravity removal",
        ),
        limitations=(
            "Accelerometer captures total body acceleration, not purely centripetal",
            "Diverges when r < 0.5 m or v ~ 0",
        ),
        category="physics",
    ),
    "turn_angle": MetricDefinition(
        name="Turn Angle",
        equation="theta = integral(omega, dt)",
        variables={
            "theta": "integrated turn angle (rad, displayed as degrees)",
            "omega": "instantaneous angular velocity (rad/s)",
            "t": "time (s)",
        },
        source="Kinematic definition of angular displacement",
        assumptions=(
            "Gyro z-axis aligned with vertical rotation axis",
            "Turn boundaries correctly identified",
            "Gyroscope bias negligible over turn duration",
        ),
        limitations=(
            "Accumulated drift in long turns (>5 s)",
            "Trapezoidal discretization error O(h^2)",
        ),
        category="physics",
    ),
    "symmetry": MetricDefinition(
        name="Turn Symmetry",
        equation="symmetry = max(0, 1 - |t_peak - t_mid| / (T/2))",
        variables={
            "t_peak": "time of peak angular velocity (s)",
            "t_mid": "temporal midpoint of turn (s)",
            "T": "turn duration (s)",
        },
        source="Heuristic proxy for biomechanical turn symmetry (PSIA)",
        assumptions=(
            "Peak angular velocity is a meaningful turn apex proxy",
            "Temporal centering indicates balanced initiation/completion",
        ),
        limitations=(
            "Asymmetric terrain naturally shifts apex",
            "Very short turns have few samples, making ratio noisy",
            "Does not capture spatial symmetry",
        ),
        category="heuristic",
    ),
    "edge_angle": MetricDefinition(
        name="Edge Angle (Roll Range)",
        equation="edge_range = roll_max - roll_min",
        variables={
            "roll_max": "maximum roll angle in turn (rad)",
            "roll_min": "minimum roll angle in turn (rad)",
        },
        source="Heuristic: phone roll correlates with body lateral inclination",
        assumptions=(
            "Phone remains in consistent pocket orientation",
            "Roll variation reflects lateral body inclination",
            "Body roll and ski edge angle are approximately linearly related",
        ),
        limitations=(
            "NOT a direct edge angle measurement",
            "Phone movement in pocket introduces artifacts",
            "Nonlinear at high edge angles (>60 deg)",
        ),
        category="heuristic",
    ),
    "turn_rhythm": MetricDefinition(
        name="Turn Rhythm",
        equation="rhythm = 1 - CV(T_1, ..., T_n) = 1 - sigma_T / mean_T",
        variables={
            "sigma_T": "std deviation of turn durations (s)",
            "mean_T": "mean turn duration (s)",
            "n": "number of turns",
        },
        source="Coaching heuristic (PSIA): rhythmic execution indicates flow",
        assumptions=(
            "All turns are comparable (same terrain type)",
            "Duration variation reflects technique, not terrain",
        ),
        limitations=(
            "Mixed terrain inflates CV artificially",
            "Unreliable with fewer than 5 turns",
        ),
        category="heuristic",
    ),
    "speed_loss_ratio": MetricDefinition(
        name="Speed Loss Ratio",
        equation="speed_loss = (v_init - v_finish) / v_init",
        variables={
            "v_init": "speed at turn initiation (m/s)",
            "v_finish": "speed at turn finish (m/s)",
        },
        source="Energy dissipation during a turn",
        assumptions=(
            "Speed measurements at initiation and finish are accurate",
            "Turn boundaries are correctly placed by phase detection",
        ),
        limitations=(
            "Returns None when v_init < 1.0 m/s",
            "Gravity on steep slopes can mask friction losses",
            "GPS 1 Hz may miss exact initiation/finish moments",
        ),
        category="physics",
    ),
    "torso_rotation_ratio": MetricDefinition(
        name="Torso Rotation Ratio",
        equation="torso_ratio = (omega_peak * T) / |theta|",
        variables={
            "omega_peak": "peak angular velocity (rad/s)",
            "T": "turn duration (s)",
            "theta": "integrated turn angle (deg)",
        },
        source="Biomechanical proxy: edge-driven vs steering-driven turns",
        assumptions=(
            "omega_peak * T approximates total torso rotation (rectangular upper bound)",
            "Turn angle represents the ski's arc",
        ),
        limitations=(
            "Rectangular approximation overestimates rotation",
            "Diverges when theta ~ 0 (guarded)",
        ),
        category="physics",
    ),
}


def get_metric(name: str) -> MetricDefinition:
    """Look up a metric by name. Raises KeyError if not found."""
    return METRICS[name]


def list_metrics() -> list[str]:
    """Return sorted list of all registered metric names."""
    return sorted(METRICS.keys())
