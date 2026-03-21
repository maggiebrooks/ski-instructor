"""Carving phase detection and phase-aware metrics feature module.

Detects intra-turn phases (initiation / apex / finish) via gyro_z
zero-crossings and computes carving-specific metrics: edge-build
progressiveness, radius stability CoV, and speed loss ratio.
"""

import numpy as np

from features.modules.base import FeatureModule


# ------------------------------------------------------------------
# Standalone helpers (importable for direct use and testing)
# ------------------------------------------------------------------

def detect_turn_phases(gyro_z_values, peak_pos):
    """Find initiation and finish boundaries of a turn via zero-crossings.

    Searches backward/forward from *peak_pos* in the signed ``gyro_z``
    signal for the nearest zero-crossing.  Falls back to segment
    boundaries when no crossing is found.

    Returns ``(init_pos, finish_pos)`` as positional indices.
    """
    n = len(gyro_z_values)
    if n < 3:
        return (0, max(0, n - 1))

    signs = np.sign(gyro_z_values)

    init_pos = 0
    for i in range(peak_pos, 0, -1):
        if signs[i] != signs[i - 1]:
            init_pos = i
            break

    finish_pos = n - 1
    for i in range(peak_pos, n - 1):
        if signs[i] != signs[i + 1]:
            finish_pos = i
            break

    return (init_pos, finish_pos)


def compute_carving_metrics(segment, init_pos, apex_pos, finish_pos):
    """Compute carving-specific metrics for one turn using phase boundaries.

    Parameters
    ----------
    segment : DataFrame
        Turn segment with ``seconds``, ``gyro_z``, ``speed``, ``roll``.
    init_pos, apex_pos, finish_pos : int
        Positional indices (iloc-based) for the three phase boundaries.

    Returns a dict with ``edge_build_progressiveness``,
    ``radius_stability_cov``, and ``speed_loss_ratio`` (each may be None
    if guards trigger).
    """
    secs = segment["seconds"].values
    gz = segment["gyro_z"].values
    speed = segment["speed"].values
    roll = segment["roll"].values

    edge_build = None
    if apex_pos > init_pos:
        phase_secs = secs[init_pos:apex_pos + 1]
        phase_roll = roll[init_pos:apex_pos + 1]
        if len(phase_secs) >= 2:
            dt = phase_secs[-1] - phase_secs[0]
            if dt > 0:
                slope = np.polyfit(phase_secs - phase_secs[0],
                                   phase_roll, 1)[0]
                edge_build = round(float(abs(np.degrees(slope))), 1)

    radius_cov = None
    phase_gz = np.abs(gz[init_pos:finish_pos + 1])
    phase_speed = speed[init_pos:finish_pos + 1]
    valid = (phase_gz > 0.1) & (phase_speed > 1.0)
    if valid.sum() >= 3:
        radii = np.clip(phase_speed[valid] / phase_gz[valid], 0, 200)
        mean_r = float(np.mean(radii))
        if mean_r > 0:
            radius_cov = round(float(np.std(radii) / mean_r), 2)

    speed_loss = None
    sp_init = float(speed[init_pos])
    sp_finish = float(speed[finish_pos])
    if sp_init > 1.0 and sp_finish >= 0:
        speed_loss = round(float((sp_init - sp_finish) / sp_init), 3)

    return {
        "edge_build_progressiveness": edge_build,
        "radius_stability_cov": radius_cov,
        "speed_loss_ratio": speed_loss,
    }


# ------------------------------------------------------------------
# Feature module
# ------------------------------------------------------------------

class CarvingPhaseModule(FeatureModule):
    """Phase detection + carving metrics from the pelvis IMU."""

    name = "carving_phase"

    def compute(self, turn_df, context):
        peak_pos = context["peak_pos"]
        secs = turn_df["seconds"].values

        init_pos, finish_pos = detect_turn_phases(
            turn_df["gyro_z"].values, peak_pos)

        carving = compute_carving_metrics(
            turn_df, init_pos, peak_pos, finish_pos)

        return {
            "initiation_start_time": round(float(secs[init_pos]), 2),
            "apex_time": round(float(secs[peak_pos]), 2),
            "finish_end_time": round(float(secs[finish_pos]), 2),
            "pelvis_edge_build_progressiveness":
                carving["edge_build_progressiveness"],
            "pelvis_radius_stability_cov":
                carving["radius_stability_cov"],
            "speed_loss_ratio": carving["speed_loss_ratio"],
        }
