import os
import re
import json
import logging
import sys

import numpy as np
import pandas as pd
from scipy.integrate import trapezoid
from scipy.signal import butter, sosfiltfilt, find_peaks
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from data.database import init_db, insert_session, insert_run, insert_turn
from features.modules.pelvis_turn_module import PelvisTurnModule
from features.modules.carving_phase_module import (
    CarvingPhaseModule,
    detect_turn_phases,
    compute_carving_metrics,
)

logger = logging.getLogger(__name__)

PROCESSING_VERSION = "2.0.0"

ACTIVE_FEATURE_MODULES = [
    PelvisTurnModule(),
    CarvingPhaseModule(),
]

# Primary IMU sensors: inner-joined on exact nanosecond timestamp
IMU_SENSORS = {
    "Accelerometer.csv": "accel",
    "Gyroscope.csv": "gyro",
}

# Secondary sensors: merged via nearest-timestamp onto the IMU timeline
SECONDARY_SENSORS = {
    "Gravity.csv": {
        "prefix": "gravity",
        "keep": None,
    },
    "Orientation.csv": {
        "prefix": None,
        "keep": ["yaw", "roll", "pitch"],
    },
    "Location.csv": {
        "prefix": None,
        "keep": [
            "latitude", "longitude", "altitude",
            "altitudeAboveMeanSeaLevel", "speed", "bearing",
            "horizontalAccuracy", "verticalAccuracy",
        ],
    },
    "Barometer.csv": {
        "prefix": None,
        "keep": ["pressure", "relativeAltitude"],
    },
    "Compass.csv": {
        "prefix": None,
        "keep": ["magneticBearing"],
    },
}

ACTIVITY_COLORS = {
    "skiing": "#4a90d9",
    "lift": "#d94a4a",
    "idle": "#cccccc",
}


# ---------------------------------------------------------------------------
# 1. Ingestion
# ---------------------------------------------------------------------------

def load_sensor_file(filepath, prefix=None):
    """Load a Sensor Logger sensor CSV. If *prefix* is given, rename x/y/z columns."""
    df = pd.read_csv(filepath)
    if "seconds_elapsed" in df.columns:
        df = df.drop(columns=["seconds_elapsed"])
    if prefix and {"x", "y", "z"}.issubset(df.columns):
        df = df.rename(columns={
            "x": f"{prefix}_x",
            "y": f"{prefix}_y",
            "z": f"{prefix}_z",
        })
    return df


def load_session(session_dir):
    """Merge all Sensor Logger sensor CSVs into one time-aligned DataFrame.

    Accelerometer and Gyroscope (both 100 Hz) are inner-joined on the
    nanosecond ``time`` column.  Lower-rate sensors (Location, Barometer,
    Orientation, Gravity, Compass) are attached via ``merge_asof`` so
    each IMU row gets the nearest reading from those sensors.
    """
    imu_frames = []
    for filename, prefix in IMU_SENSORS.items():
        path = os.path.join(session_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required sensor missing: {path}")
        imu_frames.append(load_sensor_file(path, prefix=prefix))

    merged = imu_frames[0]
    for frame in imu_frames[1:]:
        merged = pd.merge(merged, frame, on="time", how="inner")
    merged = merged.sort_values("time").reset_index(drop=True)

    for filename, cfg in SECONDARY_SENSORS.items():
        path = os.path.join(session_dir, filename)
        if not os.path.exists(path):
            logger.info("Skipping missing sensor: %s", filename)
            continue

        df = load_sensor_file(path, prefix=cfg.get("prefix"))

        keep = ["time"]
        if cfg.get("prefix"):
            p = cfg["prefix"]
            keep += [c for c in df.columns if c.startswith(f"{p}_")]
        elif cfg.get("keep"):
            keep += [c for c in cfg["keep"] if c in df.columns]
        df = df[[c for c in keep if c in df.columns]]

        df = df.sort_values("time").drop_duplicates(subset="time").reset_index(drop=True)
        merged = pd.merge_asof(merged, df, on="time", direction="nearest")

    logger.info("Loaded session: %d rows, %d columns", *merged.shape)
    return merged


def discover_sessions(data_dir):
    """Return a sorted list of Sensor Logger session directories under *data_dir*.

    A directory qualifies if it contains both Accelerometer.csv and
    Gyroscope.csv.
    """
    sessions = []
    for name in sorted(os.listdir(data_dir)):
        candidate = os.path.join(data_dir, name)
        if not os.path.isdir(candidate):
            continue
        if (os.path.exists(os.path.join(candidate, "Accelerometer.csv"))
                and os.path.exists(os.path.join(candidate, "Gyroscope.csv"))):
            sessions.append(candidate)
    return sessions


# ---------------------------------------------------------------------------
# 2. Preprocessing
# ---------------------------------------------------------------------------

def preprocess(df, source_hz=100, cutoff=5.0, order=2, target_hz=20):
    """Timestamp normalisation, Butterworth low-pass filter, down-sample."""
    df = df.copy()

    df["timestamp"] = pd.to_datetime(df["time"], unit="ns")
    df["seconds"] = (df["time"] - df["time"].iloc[0]) / 1e9

    filter_cols = [
        c for c in df.columns
        if c.startswith(("accel_", "gyro_"))
        and c.split("_")[-1] in ("x", "y", "z")
    ]
    sos = butter(order, cutoff, btype="low", fs=source_hz, output="sos")
    for col in filter_cols:
        df[col] = sosfiltfilt(sos, df[col].values)

    step = max(1, source_hz // target_hz)
    df = df.iloc[::step].reset_index(drop=True)

    logger.info("Preprocessed: %d rows at %dHz, LP-filtered at %.1fHz",
                len(df), target_hz, cutoff)
    return df


# ---------------------------------------------------------------------------
# 3. Feature engineering
# ---------------------------------------------------------------------------

def compute_row_features(df):
    """Append accel_mag and gyro_mag columns."""
    df = df.copy()
    df["accel_mag"] = np.sqrt(
        df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2
    )
    df["gyro_mag"] = np.sqrt(
        df["gyro_x"] ** 2 + df["gyro_y"] ** 2 + df["gyro_z"] ** 2
    )
    return df


def compute_turn_metrics(segment, peak_pos, sample_rate=20):
    """Compute per-turn quality metrics via the feature module system.

    Delegates to ``ACTIVE_FEATURE_MODULES`` and merges results.
    Backward-compatible: same signature and return dict as before.
    """
    context = {"peak_pos": peak_pos, "sample_rate": sample_rate}
    result = {}
    for module in ACTIVE_FEATURE_MODULES:
        result.update(module.compute(segment, context))
    return result


def compute_pelvis_turn_metrics(segment, peak_pos, sample_rate=20):
    """Pelvis-sensor wrapper — delegates to compute_turn_metrics."""
    return compute_turn_metrics(segment, peak_pos, sample_rate)


# ---------------------------------------------------------------------------
# 4. Run / lift / idle segmentation
# ---------------------------------------------------------------------------

def segment_runs(df, window_s=30, descent_thresh=-0.3, ascent_thresh=0.3,
                 min_segment_s=30, sample_rate=20):
    """Classify each row as ``skiing``, ``lift``, or ``idle``.

    Uses the barometric ``relativeAltitude`` rate of change over a rolling
    window.  Falls back to GPS ``altitude`` (noisier) or treats the entire
    session as one skiing run when no altitude source is available.

    Adds columns: ``alt_rate``, ``activity``, ``run_id``.
    """
    df = df.copy()
    window = int(window_s * sample_rate)

    alt_col = None
    for candidate in ("relativeAltitude", "altitudeAboveMeanSeaLevel", "altitude"):
        if candidate in df.columns and df[candidate].notna().any():
            alt_col = candidate
            break

    if alt_col is None:
        logger.warning(
            "No altitude column found — treating entire session as one skiing run"
        )
        df["alt_rate"] = 0.0
        df["activity"] = "skiing"
        df["run_id"] = 1
        return df

    if alt_col != "relativeAltitude":
        logger.info("Barometer missing; falling back to GPS column '%s'", alt_col)

    alt = pd.Series(df[alt_col].values)
    secs = pd.Series(df["seconds"].values)
    alt_rate = alt.diff(window) / secs.diff(window)
    alt_rate = alt_rate.bfill()

    activity = pd.Series("idle", index=df.index)
    activity = activity.where(alt_rate >= descent_thresh, "skiing")
    activity = activity.where(alt_rate <= ascent_thresh, "lift")

    # Remove short-lived segment flickers
    min_samples = int(min_segment_s * sample_rate)
    segment_id = (activity != activity.shift()).cumsum()
    seg_sizes = segment_id.map(segment_id.value_counts())
    short = seg_sizes < min_samples
    activity[short] = np.nan
    activity = activity.ffill().bfill()

    df["alt_rate"] = alt_rate.values
    df["activity"] = activity.values

    # Assign incrementing run_id to each contiguous skiing block
    is_ski = df["activity"] == "skiing"
    ski_start = is_ski & (~is_ski.shift(fill_value=False))
    df["run_id"] = np.where(is_ski, ski_start.cumsum(), 0)

    n_runs = df.loc[is_ski, "run_id"].nunique()
    logger.info("Segmented: %d skiing runs, %d lift rides",
                n_runs,
                (df["activity"] == "lift").sum() // max(1, sample_rate * 60))
    return df


# ---------------------------------------------------------------------------
# 5. Turn detection
# ---------------------------------------------------------------------------

def detect_turns(df, column="gyro_z", height=0.5, distance=20):
    """Peak-detection on the absolute gyro signal.

    Returns
    -------
    peak_indices : ndarray  — row indices (into *df*) of detected peaks
    segments : list[DataFrame]  — one per turn, sliced at midpoints
    """
    signal = df[column].abs().values
    peak_indices, _ = find_peaks(signal, height=height, distance=distance)

    boundaries = [0]
    for i in range(len(peak_indices) - 1):
        boundaries.append((peak_indices[i] + peak_indices[i + 1]) // 2)
    boundaries.append(len(df))

    segments = [
        df.iloc[boundaries[i]:boundaries[i + 1]].copy()
        for i in range(len(boundaries) - 1)
        if boundaries[i] < boundaries[i + 1]
    ]

    logger.info("Detected %d turns", len(peak_indices))
    return peak_indices, segments


def detect_turns_by_run(df, column="gyro_z", height=0.5, distance=20,
                        sample_rate=20):
    """Run turn detection independently on each skiing run.

    Returns the input DataFrame with a ``turn_peak`` boolean column added,
    plus a list of per-run result dicts (each containing a ``per_turn`` list
    with quality metrics).
    """
    df = df.copy()
    df["turn_peak"] = False

    run_results = []
    run_ids = sorted(df.loc[df["activity"] == "skiing", "run_id"].unique())

    for rid in run_ids:
        run_mask = df["run_id"] == rid
        run_df = df.loc[run_mask].reset_index(drop=True)
        original_idx = df.index[run_mask]

        peaks, segments = detect_turns(run_df, column=column,
                                       height=height, distance=distance)

        if len(peaks) > 0:
            df.loc[original_idx[peaks], "turn_peak"] = True

        # Per-turn quality metrics (via feature module system)
        per_turn = []
        for turn_idx, (peak, seg) in enumerate(zip(peaks, segments)):
            peak_pos_in_seg = int(np.searchsorted(
                seg["seconds"].values,
                run_df["seconds"].iloc[peak],
            ))
            peak_pos_in_seg = min(peak_pos_in_seg, len(seg) - 1)

            context = {
                "peak_pos": peak_pos_in_seg,
                "sample_rate": sample_rate,
                "run_index": int(rid),
                "schema_version": PROCESSING_VERSION,
            }
            metrics = {}
            for module in ACTIVE_FEATURE_MODULES:
                metrics.update(module.compute(seg, context))
            metrics["turn_id"] = turn_idx + 1
            per_turn.append(metrics)

        # Run-level basics
        run_start_s = run_df["seconds"].iloc[0]
        run_end_s = run_df["seconds"].iloc[-1]
        duration = run_end_s - run_start_s

        _alt_col = next(
            (c for c in ("altitudeAboveMeanSeaLevel", "altitude", "relativeAltitude")
             if c in run_df.columns and run_df[c].notna().any()),
            None,
        )
        alt_start = run_df[_alt_col].iloc[0] if _alt_col else None
        alt_end = run_df[_alt_col].iloc[-1] if _alt_col else None

        valid_speed = run_df.loc[run_df["speed"] >= 0, "speed"] if "speed" in run_df.columns else pd.Series(dtype=float)

        # Run-level turn quality aggregates
        angles = [t["pelvis_turn_angle_deg"] for t in per_turn]
        radii = [t["pelvis_turn_radius_m"] for t in per_turn if t["pelvis_turn_radius_m"] is not None]
        edge_angles = [t["pelvis_max_roll_angle_deg"] for t in per_turn]
        apex_speeds = [t["speed_at_apex_kmh"] for t in per_turn]
        symmetries = [t["pelvis_symmetry"] for t in per_turn]

        run_results.append({
            "run_id": int(rid),
            "start_s": round(float(run_start_s), 1),
            "end_s": round(float(run_end_s), 1),
            "duration_s": round(float(duration), 1),
            "vertical_drop_m": round(float(alt_start - alt_end), 1) if alt_start is not None and alt_end is not None else None,
            "num_turns": int(len(peaks)),
            "avg_speed_ms": round(float(valid_speed.mean()), 2) if len(valid_speed) > 0 else 0,
            "max_speed_ms": round(float(valid_speed.max()), 2) if len(valid_speed) > 0 else 0,
            "max_speed_kmh": round(float(valid_speed.max() * 3.6), 1) if len(valid_speed) > 0 else 0,
            "mean_accel_mag": round(float(run_df["accel_mag"].mean()), 3),
            "max_accel_mag": round(float(run_df["accel_mag"].max()), 3),

            "avg_turn_angle_deg": round(float(np.mean(np.abs(angles))), 1) if angles else 0,
            "avg_turn_radius_m": round(float(np.mean(radii)), 1) if radii else None,
            "avg_edge_angle_deg": round(float(np.mean(edge_angles)), 1) if edge_angles else 0,
            "avg_speed_at_apex_kmh": round(float(np.mean(apex_speeds)), 1) if apex_speeds else 0,
            "avg_symmetry": round(float(np.mean(symmetries)), 2) if symmetries else 0,
            "turns_left": sum(1 for t in per_turn if t["direction"] == "left"),
            "turns_right": sum(1 for t in per_turn if t["direction"] == "right"),

            "per_turn": per_turn,
        })

    total_turns = sum(r["num_turns"] for r in run_results)
    logger.info("Detected %d turns across %d runs", total_turns, len(run_results))
    return df, run_results


# ---------------------------------------------------------------------------
# 6. Session summary
# ---------------------------------------------------------------------------

def compute_session_summary(df, run_results, sample_rate=20, output_path=None):
    """Build session-level and per-run summary dict."""
    total_s = (df["time"].iloc[-1] - df["time"].iloc[0]) / 1e9
    ski_rows = (df["activity"] == "skiing").sum()
    lift_rows = (df["activity"] == "lift").sum()
    idle_rows = (df["activity"] == "idle").sum()

    total_turns = sum(r["num_turns"] for r in run_results)
    run_durations = [r["duration_s"] for r in run_results]
    vert_drops = [r["vertical_drop_m"] for r in run_results]

    # Collect all per-turn metrics across runs for session-level aggregates
    all_turns = [t for r in run_results for t in r.get("per_turn", [])]
    all_angles = [abs(t["pelvis_turn_angle_deg"]) for t in all_turns]
    all_radii = [t["pelvis_turn_radius_m"] for t in all_turns if t["pelvis_turn_radius_m"] is not None]
    all_apex_speeds = [t["speed_at_apex_kmh"] for t in all_turns]
    all_symmetries = [t["pelvis_symmetry"] for t in all_turns]
    turns_left = sum(1 for t in all_turns if t["direction"] == "left")
    turns_right = sum(1 for t in all_turns if t["direction"] == "right")

    summary = {
        "schema_version": PROCESSING_VERSION,
        "session_duration_s": round(float(total_s), 2),
        "total_samples": len(df),
        "sample_rate_hz": sample_rate,

        "time_skiing_s": round(ski_rows / sample_rate, 1),
        "time_lift_s": round(lift_rows / sample_rate, 1),
        "time_idle_s": round(idle_rows / sample_rate, 1),

        "num_runs": len(run_results),
        "total_turns": total_turns,
        "total_vertical_m": round(float(sum(vert_drops)), 1) if vert_drops else 0,

        "avg_run_duration_s": round(float(np.mean(run_durations)), 1) if run_durations else 0,
        "avg_run_vertical_m": round(float(np.mean(vert_drops)), 1) if vert_drops else 0,
        "avg_turns_per_run": round(total_turns / len(run_results), 1) if run_results else 0,

        "max_speed_kmh": round(float(max(r["max_speed_kmh"] for r in run_results)), 1) if run_results else 0,

        "avg_turn_angle_deg": round(float(np.mean(all_angles)), 1) if all_angles else 0,
        "avg_turn_radius_m": round(float(np.mean(all_radii)), 1) if all_radii else None,
        "avg_speed_at_apex_kmh": round(float(np.mean(all_apex_speeds)), 1) if all_apex_speeds else 0,
        "avg_symmetry": round(float(np.mean(all_symmetries)), 2) if all_symmetries else 0,
        "total_turns_left": turns_left,
        "total_turns_right": turns_right,

        "runs": run_results,
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info("Summary saved to %s", output_path)

    return summary


# ---------------------------------------------------------------------------
# 7. Visualisation
# ---------------------------------------------------------------------------

def _shade_activity(ax, df):
    """Add background shading by activity type."""
    activity = df["activity"].values
    seconds = df["seconds"].values
    changes = np.where(activity[:-1] != activity[1:])[0]
    boundaries = np.concatenate([[0], changes + 1, [len(df)]])

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = min(boundaries[i + 1], len(df) - 1)
        act = activity[start]
        color = ACTIVITY_COLORS.get(act, "#ffffff")
        ax.axvspan(seconds[start], seconds[end], alpha=0.12, color=color,
                   linewidth=0)


def plot_session(df, output_path, run_results=None):
    """Five-panel session overview with activity shading and turn markers."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fig, axes = plt.subplots(5, 1, figsize=(18, 17), sharex=True)

    # Panel 1: Altitude profile
    _plot_alt_col = next(
        (c for c in ("altitudeAboveMeanSeaLevel", "altitude", "relativeAltitude")
         if c in df.columns and df[c].notna().any()),
        None,
    )
    if _plot_alt_col:
        axes[0].plot(df["seconds"], df[_plot_alt_col],
                     linewidth=0.8, color="tab:brown")
    _shade_activity(axes[0], df)
    axes[0].set_ylabel("Altitude (m)")
    axes[0].set_title("Altitude Profile  (blue = skiing, red = lift, grey = idle)")
    axes[0].grid(True, alpha=0.3)

    # Panel 2: Gyro Z with turn peaks
    axes[1].plot(df["seconds"], df["gyro_z"], linewidth=0.4, color="tab:blue",
                 alpha=0.7)
    if "turn_peak" in df.columns:
        peaks = df[df["turn_peak"]]
        axes[1].plot(peaks["seconds"], peaks["gyro_z"], "rv", markersize=3,
                     label=f"turns ({len(peaks)})")
        axes[1].legend(loc="upper right")
    _shade_activity(axes[1], df)
    axes[1].set_ylabel("Gyro Z (rad/s)")
    axes[1].set_title("Turn Detection — Gyroscope Z-Axis (skiing runs only)")
    axes[1].grid(True, alpha=0.3)

    # Panel 3: Speed
    if "speed" in df.columns:
        valid_speed = df["speed"].copy()
        valid_speed[valid_speed < 0] = np.nan
        axes[2].plot(df["seconds"], valid_speed * 3.6, linewidth=0.5,
                     color="tab:purple")
    _shade_activity(axes[2], df)
    axes[2].set_ylabel("Speed (km/h)")
    axes[2].set_title("GPS Speed")
    axes[2].grid(True, alpha=0.3)

    # Panel 4: Acceleration magnitude
    axes[3].plot(df["seconds"], df["accel_mag"], linewidth=0.4,
                 color="tab:orange")
    _shade_activity(axes[3], df)
    axes[3].set_ylabel("Accel Magnitude (m/s²)")
    axes[3].set_title("Linear Acceleration Magnitude")
    axes[3].grid(True, alpha=0.3)

    # Panel 5: Turn radius scatter (from per-turn metrics)
    _shade_activity(axes[4], df)
    if run_results:
        left_t, left_r, right_t, right_r = [], [], [], []
        for run in run_results:
            for turn in run.get("per_turn", []):
                if turn["pelvis_turn_radius_m"] is None:
                    continue
                if turn["direction"] == "left":
                    left_t.append(turn["time_s"])
                    left_r.append(turn["pelvis_turn_radius_m"])
                else:
                    right_t.append(turn["time_s"])
                    right_r.append(turn["pelvis_turn_radius_m"])
        if left_t:
            axes[4].scatter(left_t, left_r, s=12, alpha=0.6, color="#e74c3c",
                            label=f"left ({len(left_t)})", zorder=3)
        if right_t:
            axes[4].scatter(right_t, right_r, s=12, alpha=0.6, color="#3498db",
                            label=f"right ({len(right_t)})", zorder=3)
        axes[4].legend(loc="upper right")
    axes[4].set_ylabel("Turn Radius (m)")
    axes[4].set_title("Turn Radius by Direction  (smaller = tighter carve)")
    axes[4].set_ylim(bottom=0)
    axes[4].grid(True, alpha=0.3)

    axes[-1].set_xlabel("Time (seconds)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("Plot saved to %s", output_path)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def process_one_session(session_dir, processed_dir, output_dir,
                        session_label=None):
    """Run the full pipeline on a single Sensor Logger session folder.

    Delegates entirely to :class:`ski.processing.session_processor.SessionProcessor`.
    Returns the session summary dict.
    """
    from pathlib import Path
    from ski.processing.session_processor import SessionProcessor

    if session_label is None:
        session_label = os.path.basename(session_dir)

    session_id = session_label.replace(" ", "_").replace("/", "_")
    db_path = os.path.join(os.path.dirname(processed_dir), "ski.db")

    processor = SessionProcessor(
        db_path=db_path,
        processing_version=PROCESSING_VERSION,
    )
    return processor.process(
        session_id=session_id,
        raw_path=Path(session_dir),
        processed_dir=Path(processed_dir),
        output_dir=Path(output_dir),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path
    from ski.processing.session_processor import SessionProcessor

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data")
    processed_dir = os.path.join(data_dir, "processed")
    output_dir = os.path.join(project_root, "output")
    db_path = os.path.join(data_dir, "ski.db")

    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    sessions = discover_sessions(data_dir)
    logger.info("Found %d session(s):", len(sessions))
    for s in sessions:
        logger.info("  - %s", os.path.basename(s))

    processor = SessionProcessor(
        db_path=db_path,
        processing_version=PROCESSING_VERSION,
    )

    all_summaries = {}
    for session_dir in sessions:
        label = os.path.basename(session_dir)
        session_id = label.replace(" ", "_").replace("/", "_")
        summary = processor.process(
            session_id=session_id,
            raw_path=Path(session_dir),
            processed_dir=Path(processed_dir),
            output_dir=Path(output_dir),
        )
        all_summaries[label] = summary

    overview_path = os.path.join(processed_dir, "all_sessions_overview.json")
    with open(overview_path, "w") as f:
        json.dump(all_summaries, f, indent=2)

    logger.info("All sessions complete. Overview saved -> %s", overview_path)
