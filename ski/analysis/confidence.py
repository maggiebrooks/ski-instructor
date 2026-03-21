"""Per-metric confidence scoring.

Maps data quality indicators and per-turn input values to a [0, 1]
confidence score for each computed metric.  The rules are deterministic
and derive from the physical validity constraints documented in
``docs/math.md``.
"""

from __future__ import annotations

import numpy as np

from ski.analysis.metric_provenance import METRICS


def compute_metric_confidence(
    metric_name: str,
    inputs: dict,
    data_quality: dict,
) -> float:
    """Compute confidence for a single metric value.

    Parameters
    ----------
    metric_name : str
        Key into the METRICS registry (e.g. ``"turn_radius"``).
    inputs : dict
        Metric-specific input values.  Expected keys depend on the
        metric (documented per-rule below).
    data_quality : dict
        Output of ``evaluate_data_quality()``.

    Returns
    -------
    float
        Confidence in [0, 1].
    """
    rule = _RULES.get(metric_name)
    if rule is None:
        defn = METRICS.get(metric_name)
        if defn is not None and defn.category == "heuristic":
            return 0.5
        return 0.7

    return float(np.clip(rule(inputs, data_quality), 0.0, 1.0))


def compute_turn_confidence(
    metrics_dict: dict,
    data_quality: dict,
) -> dict:
    """Compute confidence scores for all metrics in a turn/session dict.

    Parameters
    ----------
    metrics_dict : dict
        Flat dict of metric values (e.g. from scores or per-turn output).
        Keys are checked against the METRICS registry.
    data_quality : dict
        Output of ``evaluate_data_quality()``.

    Returns
    -------
    dict
        ``{metric_name: confidence_float}`` for every metric found
        in both ``metrics_dict`` and the registry.
    """
    result = {}
    for metric_name in METRICS:
        if metric_name not in _INPUT_EXTRACTORS:
            continue
        inputs = _INPUT_EXTRACTORS[metric_name](metrics_dict)
        if inputs is None:
            continue
        result[metric_name] = round(
            compute_metric_confidence(metric_name, inputs, data_quality), 4
        )
    return result


# ------------------------------------------------------------------
# Per-metric confidence rules
# ------------------------------------------------------------------

def _speed_confidence(inputs: dict, dq: dict) -> float:
    gps = dq.get("gps_accuracy", 0.5)
    v = inputs.get("speed", 0.0)
    if v is None or v < 0.5:
        return gps * 0.5
    return gps


def _angular_velocity_confidence(inputs: dict, dq: dict) -> float:
    omega = abs(inputs.get("omega", 0.0) or 0.0)
    gyro_q = dq.get("gyro_quality", 0.5)
    signal_factor = np.clip(omega / 0.5, 0, 1)
    return float(gyro_q * 0.6 + signal_factor * 0.4)


def _turn_radius_confidence(inputs: dict, dq: dict) -> float:
    omega = abs(inputs.get("omega", 0.0) or 0.0)
    v = inputs.get("speed", 0.0) or 0.0
    gps = dq.get("gps_accuracy", 0.5)
    gyro_q = dq.get("gyro_quality", 0.5)

    if omega < 0.1 or v < 1.0:
        return 0.0

    omega_factor = np.clip((omega - 0.1) / 0.4, 0, 1)
    speed_factor = np.clip((v - 1.0) / 4.0, 0, 1)
    divisor_penalty = 1.0 if omega >= 0.5 else float(omega / 0.5)

    base = (gps * 0.3 + gyro_q * 0.3 + omega_factor * 0.2 + speed_factor * 0.2)
    return float(base * divisor_penalty)


def _centripetal_acceleration_confidence(inputs: dict, dq: dict) -> float:
    speed_conf = _speed_confidence(inputs, dq)
    radius_conf = _turn_radius_confidence(inputs, dq)
    return min(speed_conf, radius_conf)


def _pressure_ratio_confidence(inputs: dict, dq: dict) -> float:
    radius_conf = _turn_radius_confidence(inputs, dq)
    speed_conf = _speed_confidence(inputs, dq)
    r = inputs.get("radius", 5.0) or 5.0
    radius_penalty = np.clip(r / 2.0, 0, 1) if r < 2.0 else 1.0
    return float(min(radius_conf, speed_conf) * radius_penalty)


def _turn_angle_confidence(inputs: dict, dq: dict) -> float:
    sampling = dq.get("sampling_rate_stability", 0.5)
    gyro_q = dq.get("gyro_quality", 0.5)
    duration = inputs.get("duration", 1.0) or 1.0

    duration_factor = 1.0
    if duration < 0.5:
        duration_factor = duration / 0.5
    elif duration > 5.0:
        duration_factor = np.clip(5.0 / duration, 0.5, 1.0)

    return float((sampling * 0.4 + gyro_q * 0.4 + 0.2) * duration_factor)


def _symmetry_confidence(inputs: dict, dq: dict) -> float:
    duration = inputs.get("duration", 1.0) or 1.0
    base = 0.5
    if duration >= 1.0:
        base = 0.65
    elif duration < 0.5:
        base = 0.3
    return base


def _edge_angle_confidence(inputs: dict, dq: dict) -> float:
    return 0.5


def _turn_rhythm_confidence(inputs: dict, dq: dict) -> float:
    n_turns = inputs.get("n_turns", 0) or 0
    if n_turns < 5:
        return 0.2
    return float(np.clip(0.4 + 0.1 * min(n_turns, 6), 0, 1))


def _speed_loss_confidence(inputs: dict, dq: dict) -> float:
    gps = dq.get("gps_accuracy", 0.5)
    v_init = inputs.get("v_init", 0.0) or 0.0
    if v_init < 1.0:
        return 0.0
    speed_factor = np.clip((v_init - 1.0) / 4.0, 0, 1)
    return float(gps * 0.6 + speed_factor * 0.4)


def _torso_rotation_confidence(inputs: dict, dq: dict) -> float:
    angle_conf = _turn_angle_confidence(inputs, dq)
    omega_conf = _angular_velocity_confidence(inputs, dq)
    return min(angle_conf, omega_conf)


_RULES = {
    "speed": _speed_confidence,
    "angular_velocity": _angular_velocity_confidence,
    "turn_radius": _turn_radius_confidence,
    "centripetal_acceleration": _centripetal_acceleration_confidence,
    "pressure_ratio": _pressure_ratio_confidence,
    "turn_angle": _turn_angle_confidence,
    "symmetry": _symmetry_confidence,
    "edge_angle": _edge_angle_confidence,
    "turn_rhythm": _turn_rhythm_confidence,
    "speed_loss_ratio": _speed_loss_confidence,
    "torso_rotation_ratio": _torso_rotation_confidence,
}


# ------------------------------------------------------------------
# Input extractors -- pull relevant values from a scores/metrics dict
# ------------------------------------------------------------------

def _extract_speed(m: dict) -> dict | None:
    v = m.get("max_speed_kmh") or m.get("speed_at_apex_kmh") or m.get("speed")
    if v is None:
        return None
    if isinstance(v, (int, float)):
        v_ms = v / 3.6 if v > 50 else v
    else:
        return None
    return {"speed": v_ms}


def _extract_angular_velocity(m: dict) -> dict | None:
    omega = m.get("pelvis_peak_rotation_rate") or m.get("rotary_ratio_raw")
    if omega is None:
        return None
    return {"omega": omega}


def _extract_turn_radius(m: dict) -> dict | None:
    omega = m.get("pelvis_peak_rotation_rate") or m.get("rotary_ratio_raw")
    v = m.get("speed_at_apex_kmh")
    if v is not None:
        v = v / 3.6
    elif m.get("max_speed_kmh") is not None:
        v = m["max_speed_kmh"] / 3.6
    else:
        v = m.get("speed")
    if omega is None or v is None:
        return None
    return {"omega": omega, "speed": v}


def _extract_centripetal(m: dict) -> dict | None:
    return _extract_turn_radius(m)


def _extract_pressure_ratio(m: dict) -> dict | None:
    base = _extract_turn_radius(m)
    if base is None:
        return None
    r = m.get("pelvis_turn_radius_m") or m.get("normalized_turn_radius")
    base["radius"] = r
    return base


def _extract_turn_angle(m: dict) -> dict | None:
    dur = m.get("duration_s") or m.get("duration_seconds")
    if dur is None:
        return None
    return {"duration": dur}


def _extract_symmetry(m: dict) -> dict | None:
    dur = m.get("duration_s") or m.get("duration_seconds")
    return {"duration": dur or 1.0}


def _extract_edge_angle(m: dict) -> dict | None:
    return {}


def _extract_turn_rhythm(m: dict) -> dict | None:
    n = m.get("n_turns") or m.get("turns") or m.get("total_turns")
    return {"n_turns": n or 0}


def _extract_speed_loss(m: dict) -> dict | None:
    v = m.get("speed_at_apex_kmh")
    if v is not None:
        v = v / 3.6
    else:
        v = m.get("speed") or m.get("max_speed_kmh")
        if v is not None and v > 50:
            v = v / 3.6
    return {"v_init": v or 0.0}


def _extract_torso_rotation(m: dict) -> dict | None:
    base = _extract_turn_angle(m)
    if base is None:
        base = {"duration": 1.0}
    omega = m.get("pelvis_peak_rotation_rate") or m.get("rotary_ratio_raw")
    base["omega"] = omega or 0.0
    return base


def compute_per_turn_confidence(
    row: dict | object,
    data_quality: dict,
) -> float:
    """Compute confidence for a single turn from its metrics.

    Uses turn_radius confidence (omega, speed) as the primary indicator
    of turn data quality. Falls back to 1.0 if inputs are missing.

    Parameters
    ----------
    row : dict or pandas Series
        Per-turn metrics. Expected keys: speed_at_apex (km/h),
        pelvis_peak_angular_velocity (rad/s), duration_seconds.
    data_quality : dict
        Output of evaluate_data_quality().

    Returns
    -------
    float
        Confidence in [0, 1].
    """
    if hasattr(row, "get"):
        d = row
    else:
        d = dict(row) if hasattr(row, "items") else {}
    speed_kmh = d.get("speed_at_apex")
    omega = d.get("pelvis_peak_angular_velocity")
    if speed_kmh is not None:
        speed_ms = speed_kmh / 3.6 if speed_kmh > 15 else speed_kmh
    else:
        speed_ms = 0.0
    omega = omega if omega is not None else 0.0
    inputs = {"omega": omega, "speed": speed_ms}
    return compute_metric_confidence("turn_radius", inputs, data_quality)


_INPUT_EXTRACTORS: dict[str, callable] = {
    "speed": _extract_speed,
    "angular_velocity": _extract_angular_velocity,
    "turn_radius": _extract_turn_radius,
    "centripetal_acceleration": _extract_centripetal,
    "pressure_ratio": _extract_pressure_ratio,
    "turn_angle": _extract_turn_angle,
    "symmetry": _extract_symmetry,
    "edge_angle": _extract_edge_angle,
    "turn_rhythm": _extract_turn_rhythm,
    "speed_loss_ratio": _extract_speed_loss,
    "torso_rotation_ratio": _extract_torso_rotation,
}
