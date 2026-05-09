"""One-shot comparison harness: run the pipeline through turn detection
on a single raw session, with and without ski.frame_alignment.align_session,
and print logs + turn counts. Read-only with respect to repo state aside
from a transient log capture."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from transformations.process_session import (  # noqa: E402
    compute_row_features,
    detect_turns_by_run,
    load_session,
    preprocess,
    segment_runs,
)
from ski.frame_alignment import align_session  # noqa: E402


SESSION_DIR = REPO_ROOT / "data" / "Aspen_Highlands-2026-03-06_20-19-40"


def _setup_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(name)s  %(message)s"))
    root.addHandler(h)
    root.setLevel(logging.INFO)


def run_branch(label: str, *, with_alignment: bool) -> dict:
    print()
    print("=" * 70)
    print(f"BRANCH: {label}")
    print("=" * 70)

    df = load_session(str(SESSION_DIR))
    df = preprocess(df)
    df = compute_row_features(df)

    if with_alignment:
        df = align_session(df)
        logging.getLogger(__name__).info("Frame alignment applied.")

    df = segment_runs(df)
    n_runs = df.loc[df["activity"] == "skiing", "run_id"].nunique()

    df, run_results = detect_turns_by_run(df)
    total_turns = sum(r["num_turns"] for r in run_results)

    return {
        "label": label,
        "with_alignment": with_alignment,
        "rows": int(df.shape[0]),
        "runs": int(n_runs),
        "turns": int(total_turns),
        "per_run": [
            {"run_id": r["run_id"], "num_turns": r["num_turns"]}
            for r in run_results
        ],
    }


def main() -> None:
    _setup_logging()

    if not (SESSION_DIR / "Accelerometer.csv").exists():
        raise SystemExit(f"No Accelerometer.csv at {SESSION_DIR}")

    a = run_branch("BEFORE (no align_session)", with_alignment=False)
    b = run_branch("AFTER  (with align_session)", with_alignment=True)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in (a, b):
        print(
            f"  {r['label']:<32}  rows={r['rows']:>6}  runs={r['runs']:>3}  turns={r['turns']:>4}"
        )
    print()
    print("Per-run turn counts (run_id: before -> after):")
    by_run = {x["run_id"]: x["num_turns"] for x in a["per_run"]}
    for x in b["per_run"]:
        rid = x["run_id"]
        print(f"  run {rid}: {by_run.get(rid, '-'):>4} -> {x['num_turns']:>4}")


if __name__ == "__main__":
    main()
