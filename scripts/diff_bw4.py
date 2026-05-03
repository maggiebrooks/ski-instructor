"""Synthetic side-by-side comparison of Butterworth order 2 vs order 4.

There is no raw skiing data in the repo right now (``data/raw/`` only contains
``session_1.csv``, the fake-signal artifact), so we cannot regenerate the
real-session summaries to diff. Instead we run both filters against a
representative synthetic IMU signal: a 5-Hz-bandlimited skiing-like
oscillation plus white noise, sampled at 100 Hz.

This lets us answer the engineering question: how big is the time-domain
difference between order=2 and order=4 at fc = 5 Hz, fs = 100 Hz?

If max|delta| is small relative to the signal RMS, the bump is safe to ship
even without an on-snow regression.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def make_signal(fs: int = 100, duration_s: float = 60.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * duration_s)) / fs
    body = (
        1.5 * np.sin(2 * np.pi * 0.7 * t)
        + 0.6 * np.sin(2 * np.pi * 1.4 * t + 0.3)
        + 0.3 * np.sin(2 * np.pi * 2.5 * t + 1.1)
    )
    return body + rng.normal(0.0, 0.2, t.size)


def filter_signal(x: np.ndarray, order: int, cutoff: float = 5.0, fs: int = 100) -> np.ndarray:
    sos = butter(order, cutoff, btype="low", fs=fs, output="sos")
    return sosfiltfilt(sos, x)


def main() -> int:
    fs = 100
    x = make_signal(fs=fs)
    y2 = filter_signal(x, order=2, fs=fs)
    y4 = filter_signal(x, order=4, fs=fs)

    delta = y4 - y2
    rms_x = float(np.sqrt(np.mean(x ** 2)))
    rms_y2 = float(np.sqrt(np.mean(y2 ** 2)))
    rms_d = float(np.sqrt(np.mean(delta ** 2)))

    print("Synthetic 60 s, 100 Hz, fc = 5 Hz, sosfiltfilt")
    print(f"  RMS input            {rms_x:8.4f}")
    print(f"  RMS order=2 output   {rms_y2:8.4f}")
    print(f"  RMS (y4 - y2) delta  {rms_d:8.4f}  ({100 * rms_d / rms_y2:5.2f}% of order=2 RMS)")
    print(f"  max |y4 - y2|        {float(np.max(np.abs(delta))):8.4f}")

    pct = 100 * rms_d / rms_y2
    print()
    print("Acceptance: delta RMS < 5% of order=2 RMS.")
    if pct < 5.0:
        print(f"PASS ({pct:.2f}% < 5%).  Bumping order 2 -> 4 is safe at fc = 5 Hz.")
        return 0
    print(f"FAIL ({pct:.2f}% >= 5%).  Re-evaluate threshold downstream.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
