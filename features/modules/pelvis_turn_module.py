"""Pelvis-sensor turn physics feature module.

Computes core per-turn metrics from the pelvis-mounted phone IMU:
turn angle, rotation rate, radius, roll range, g-force, and symmetry.
"""

import numpy as np
from scipy.integrate import trapezoid

from features.modules.base import FeatureModule


class PelvisTurnModule(FeatureModule):
    """Core turn physics from the pelvis (phone) IMU."""

    name = "pelvis_turn"

    def compute(self, turn_df, context):
        peak_pos = context["peak_pos"]
        sample_rate = context.get("sample_rate", 20)

        secs = turn_df["seconds"].values
        duration = (secs[-1] - secs[0] if len(secs) > 1
                    else len(secs) / sample_rate)

        angle_rad = trapezoid(turn_df["gyro_z"].values, secs)
        angle_deg = float(np.degrees(angle_rad))

        peak_row = turn_df.iloc[peak_pos]
        peak_gz = float(abs(peak_row["gyro_z"]))
        speed_ms = float(peak_row["speed"]) if peak_row["speed"] >= 0 else 0.0
        speed_kmh = speed_ms * 3.6

        if peak_gz > 0.1 and speed_ms > 1.0:
            radius = speed_ms / peak_gz
        else:
            radius = None

        edge_range_deg = float(np.degrees(
            turn_df["roll"].max() - turn_df["roll"].min()
        ))

        g_force = float(peak_row["accel_mag"] / 9.807)

        t_peak = secs[peak_pos]
        t_mid = (secs[0] + secs[-1]) / 2
        half_dur = duration / 2 if duration > 0 else 1.0
        symmetry = max(0.0, 1.0 - abs(t_peak - t_mid) / half_dur)

        return {
            "sensor_source": "pelvis_phone",
            "time_s": round(float(secs[peak_pos]), 1),
            "direction": "left" if angle_deg < 0 else "right",
            "duration_s": round(float(duration), 2),
            "speed_at_apex_kmh": round(speed_kmh, 1),
            "pelvis_turn_angle_deg": round(angle_deg, 1),
            "pelvis_peak_rotation_rate": round(peak_gz, 3),
            "pelvis_turn_radius_m": (round(radius, 1) if radius is not None
                                     else None),
            "pelvis_max_roll_angle_deg": round(edge_range_deg, 1),
            "pelvis_peak_g_force": round(g_force, 2),
            "pelvis_symmetry": round(symmetry, 2),
        }
