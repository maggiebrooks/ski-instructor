#!/usr/bin/env python3
"""Trim a Sensor Logger session ZIP to the first N seconds of each CSV.

Preserves directory layout inside the archive. Any ``.csv`` with a
``seconds_elapsed`` column is row-filtered; other members are copied unchanged.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd


def _trim_csv_bytes(raw: bytes, max_seconds: float) -> bytes:
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        return raw
    if "seconds_elapsed" not in df.columns:
        return raw
    se = pd.to_numeric(df["seconds_elapsed"], errors="coerce")
    mask = se <= max_seconds
    out = df.loc[mask].copy()
    buf = io.StringIO()
    out.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")


def trim_zip(input_path: Path, output_path: Path, max_seconds: float) -> None:
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    in_size = input_path.stat().st_size

    with zipfile.ZipFile(input_path, "r") as zin, zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.lower().endswith(".csv"):
                data = _trim_csv_bytes(data, max_seconds)
            # Preserve path and metadata where possible
            zi = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)

    out_size = output_path.stat().st_size
    print(f"Input size:  {in_size:,} bytes ({in_size / (1024 * 1024):.2f} MB)")
    print(f"Output size: {out_size:,} bytes ({out_size / (1024 * 1024):.2f} MB)")
    print(f"Duration kept: <= {max_seconds:g} s (seconds_elapsed)")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(
        description="Trim Sensor Logger ZIP CSVs to first N seconds by seconds_elapsed."
    )
    p.add_argument("input_zip", type=Path, help="Path to input .zip")
    p.add_argument("output_zip", type=Path, help="Path to output .zip")
    p.add_argument(
        "duration_s",
        nargs="?",
        type=float,
        default=180.0,
        help="Keep rows with seconds_elapsed <= this (default: 180)",
    )
    args = p.parse_args(argv)
    trim_zip(args.input_zip, args.output_zip, float(args.duration_s))


if __name__ == "__main__":
    main(sys.argv[1:])
