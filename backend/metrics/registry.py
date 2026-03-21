"""Metric registry: units, equations, references, assumptions.

Required for scientific credibility. All computed metrics must be registered.
"""

from __future__ import annotations

METRIC_REGISTRY: dict[str, dict] = {
    "turn_radius": {
        "units": "meters",
        "equation": "r = v / omega",
        "reference": "Classical mechanics, circular motion kinematics (v = omega * r)",
        "assumptions": [
            "Instantaneous circular arc at turn apex",
            "Sensor near center of mass",
            "Velocity estimation accurate",
        ],
    },
    "pressure_ratio": {
        "units": "dimensionless",
        "equation": "g_measured / (v^2 / (r * 9.81))",
        "reference": "Newtonian centripetal acceleration comparison",
        "assumptions": [
            "Circular motion at apex",
            "Accelerometer measures centripetal loading after gravity removal",
        ],
    },
    "torso_rotation_ratio": {
        "units": "dimensionless",
        "equation": "(omega_peak * T) / |theta|",
        "reference": "Biomechanical proxy for edge-driven vs steering-driven turns",
        "assumptions": [
            "omega_peak * T approximates torso rotation",
            "Turn angle represents ski arc",
        ],
    },
    "normalized_turn_radius": {
        "units": "dimensionless (radius / ski_length)",
        "equation": "r / L_ski",
        "reference": "Equipment-normalized turn size",
        "assumptions": [
            "Ski length metadata available",
            "Radius from v/omega",
        ],
    },
    "rotary_stability": {
        "units": "dimensionless (0-1)",
        "equation": "1 - clip(torso_rotation_ratio, 0, 1)",
        "reference": "PSIA Five Fundamentals, quiet upper body",
        "assumptions": [
            "Low ratio = edge-driven, high ratio = steering-driven",
        ],
    },
    "edge_consistency": {
        "units": "dimensionless (0-1)",
        "equation": "mean(1 - radius_cv, edge_prog, 1 - radius_stability)",
        "reference": "PSIA Five Fundamentals, consistent edge engagement",
        "assumptions": [
            "Radius CV, edge build, radius stability from carving module",
        ],
    },
    "pressure_management": {
        "units": "dimensionless (0-1)",
        "equation": "mean(pressure_ratio, 1 - speed_loss)",
        "reference": "PSIA Five Fundamentals, centripetal loading",
        "assumptions": [
            "Pressure ratio from physics; speed loss from phase detection",
        ],
    },
    "turn_symmetry": {
        "units": "dimensionless (0-1)",
        "equation": "mean(turn_balance, temporal_symmetry, radius_LR_symmetry)",
        "reference": "PSIA Five Fundamentals, balanced turns",
        "assumptions": [
            "Left/right balance, peak timing, radius symmetry",
        ],
    },
    "turn_shape_consistency": {
        "units": "dimensionless (0-1)",
        "equation": "mean(1 - radius_cv, 1 - angle_cv)",
        "reference": "Consistent turn shape across session",
        "assumptions": [
            "Radius and angle CV from per-turn data",
        ],
    },
    "turn_rhythm": {
        "units": "dimensionless (0-1)",
        "equation": "1 - CV(turn_durations)",
        "reference": "PSIA, rhythmic execution",
        "assumptions": [
            "Consistent terrain for comparable turns",
        ],
    },
    "turn_efficiency": {
        "units": "dimensionless (0-1)",
        "equation": "1 - speed_loss_ratio",
        "reference": "Energy conservation through turns",
        "assumptions": [
            "Speed at init/finish from phase boundaries",
        ],
    },
    "speed_loss_ratio": {
        "units": "dimensionless",
        "equation": "(v_init - v_finish) / v_init",
        "reference": "Energy dissipation during turn",
        "assumptions": [
            "Phase boundaries correctly identified",
            "GPS speed at init/finish",
        ],
    },
    "pelvis_symmetry": {
        "units": "dimensionless (0-1)",
        "equation": "max(0, 1 - |t_peak - t_mid| / (T/2))",
        "reference": "Temporal symmetry heuristic",
        "assumptions": [
            "Peak angular velocity at turn apex",
        ],
    },
    "pelvis_max_roll_angle": {
        "units": "degrees",
        "equation": "roll_max - roll_min",
        "reference": "Heuristic edge angle proxy from body inclination",
        "assumptions": [
            "Phone roll correlates with lateral inclination",
            "NOT direct ski edge measurement",
        ],
    },
    "pelvis_estimated_turn_radius": {
        "units": "meters",
        "equation": "v / omega",
        "reference": "Circular motion kinematics",
        "assumptions": [
            "Instantaneous circular arc",
            "omega > 0.1 rad/s, v > 1 m/s",
        ],
    },
    "pelvis_peak_g_force": {
        "units": "g",
        "equation": "accel_mag / 9.807",
        "reference": "Peak lateral loading",
        "assumptions": [
            "Gravity removed from accelerometer",
        ],
    },
}
