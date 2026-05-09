"""One-off: compare turn counts with vs without align_session for one session."""

import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from transformations.process_session import (
    compute_row_features,
    detect_turns_by_run,
    load_session,
    preprocess,
    segment_runs,
)
from ski.frame_alignment import align_session, estimate_gravity_vector


def run(df, label):
    df = segment_runs(df.copy())
    df, run_results = detect_turns_by_run(df)
    n = sum(r["num_turns"] for r in run_results)
    print(f"{label:<28s} runs={len(run_results)}  turns={n}  per_run={[r['num_turns'] for r in run_results]}")
    return n


def main(session_dir: str):
    print(f"Session: {session_dir}\n")

    df = load_session(session_dir)
    df = preprocess(df)
    df = compute_row_features(df)

    g = estimate_gravity_vector(df)
    print(f"Gravity estimate (sensor frame): {g}")
    print(f"  magnitude: {np.linalg.norm(g):.4f} m/s^2  ({np.linalg.norm(g)/9.81:.4f} g)")
    print(f"  accel_mag stats pre-align:  mean={df['accel_mag'].mean():.3f}  "
          f"std={df['accel_mag'].std():.3f}  max={df['accel_mag'].max():.3f}")
    print()

    n_before = run(df, "Without align_session:")
    df_aligned = align_session(df.copy())
    print(f"  accel_mag stats post-align: mean={df_aligned['accel_mag'].mean():.3f}  "
          f"std={df_aligned['accel_mag'].std():.3f}  max={df_aligned['accel_mag'].max():.3f}")
    n_after = run(df_aligned, "With align_session:")

    delta = n_after - n_before
    pct = 100.0 * delta / max(1, n_before)
    print(f"\nDelta: {delta:+d} turns ({pct:+.1f}%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/Aspen_Highlands-2026-03-06_20-19-40")
