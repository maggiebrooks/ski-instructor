#!/usr/bin/env python3
"""Create scripts/test_session.zip: minimal Sensor Logger-style IMU ZIP for upload tests.

200 rows per IMU @ 100 Hz (10 ms spacing), monotonic ``time`` in ns, columns
``time,seconds_elapsed,x,y,z``. Values sized to pass ``backend/validation/input_validator.py``.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from pathlib import Path

ROWS = 200
DT_NS = 10_000_000  # 100 Hz
# Fixed base so runs are reproducible (nanoseconds since Unix epoch).
BASE_TIME_NS = 1_704_000_000_000_000_000


def _csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _accel_rows() -> list[list]:
    rows: list[list] = []
    for i in range(ROWS):
        t = BASE_TIME_NS + i * DT_NS
        sec = i * 0.01
        # Small body-frame lateral; ~gravity on z with gentle variation (~skiing idle / pocket).
        x = 0.12 * math.sin(i * 0.07) + 0.02 * math.sin(i * 0.31)
        y = 0.09 * math.cos(i * 0.05) + 0.015 * math.cos(i * 0.27)
        z = 9.80665 + 0.25 * math.sin(i * 0.11) + 0.05 * math.cos(i * 0.19)
        rows.append([t, f"{sec:.4f}", x, y, z])
    return rows


def _gyro_rows() -> list[list]:
    rows: list[list] = []
    for i in range(ROWS):
        t = BASE_TIME_NS + i * DT_NS
        sec = i * 0.01
        # rad/s; turn-rate-ish band 0.1-0.5 with smooth variation.
        x = 0.06 * math.sin(i * 0.18)
        y = 0.04 * math.cos(i * 0.14)
        z = 0.32 + 0.14 * math.sin(i * 0.09)
        rows.append([t, f"{sec:.4f}", x, y, z])
    return rows


def main() -> None:
    root = Path(__file__).resolve().parent
    out_zip = root / "test_session.zip"
    header = ["time", "seconds_elapsed", "x", "y", "z"]

    accel_csv = _csv_bytes(header, _accel_rows())
    gyro_csv = _csv_bytes(header, _gyro_rows())

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Accelerometer.csv", accel_csv)
        zf.writestr("Gyroscope.csv", gyro_csv)

    size = out_zip.stat().st_size
    print(f"Wrote {out_zip} ({size} bytes)")


if __name__ == "__main__":
    main()
