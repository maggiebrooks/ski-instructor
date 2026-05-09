"""Static gravity-based sensor-to-body frame alignment.

The mobile recorder writes raw iOS Core Motion device-fixed axes:
``+x`` is the right of the screen, ``+y`` is the top of the screen, ``+z``
points out of the screen toward the user. With the phone in a front pocket
(screen toward the body, top up, portrait), those axes are *roughly* aligned
with the skier, but not exactly — the phone slides, rotates, and sits at an
arbitrary tilt. Today every per-turn metric (``gyro_z`` integrated as turn
angle, ``accel_mag`` interpreted as centripetal force, fused ``roll`` as edge
angle) silently assumes the sensor frame *is* the skier frame.

This module estimates a single static rotation per session that maps the
sensor frame into a body frame whose ``+z`` axis is anti-parallel to gravity.
After alignment, ``gyro_z`` is yaw rate (the meaningful turn-detection axis)
and the accelerometer minus the constant gravity contribution gives true
dynamic acceleration.

Pipeline placement: this runs at 20 Hz, after ``transformations.process_session.preprocess()``
and ``compute_row_features()`` (so ``accel_mag`` / ``gyro_mag`` already exist),
and before ``segment_runs`` / ``detect_turns`` consume any axis-meaningful values.

The alignment is *static* on purpose: a single rotation for the whole session.
Tracking phone reorientation during the session is a job for a real fusion
filter (Madgwick / Mahony / EKF) and is out of scope here.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


_GRAVITY_M_S2 = 9.81
_TARGET_DOWN = np.array([0.0, 0.0, -1.0], dtype=np.float64)


def _find_still_window_slice(
    df: pd.DataFrame,
    min_window_s: float,
    sample_rate: int,
) -> slice:
    """Locate the calmest contiguous window in the session.

    Returns a ``slice`` covering ``min_window_s * sample_rate`` rows
    centered on the index where ``gyro_mag``'s rolling minimum is smallest.
    Both gravity-source paths in this module consume this helper so they
    agree on which rows are "still":

    * ``estimate_gravity_vector`` averages ``accel_*`` over the slice when
      the accelerometer carries gravity (mobile / specific-force input).
    * ``align_session`` averages a dedicated ``gravity_*`` stream over the
      same slice when one is present (Sensor Logger iOS path).

    Falls back to ``slice(0, len(df))`` (the entire DataFrame) when:

    * ``min_window_s * sample_rate`` is non-positive,
    * ``gyro_mag`` is not in ``df`` (e.g. ``compute_row_features`` skipped),
    * ``df`` has fewer rows than the requested window, or
    * every entry of the rolling minimum is NaN.
    """
    n = len(df)
    window = int(min_window_s * sample_rate)

    if (
        window <= 0
        or "gyro_mag" not in df.columns
        or n < window
    ):
        return slice(0, n)

    rolling_min = df["gyro_mag"].rolling(window, min_periods=window).min()
    rolling_arr = rolling_min.to_numpy(dtype=np.float64)

    if np.all(np.isnan(rolling_arr)):
        return slice(0, n)

    end_of_min_window = int(np.nanargmin(rolling_arr))

    half = window // 2
    start = max(0, end_of_min_window - half)
    end = min(n, start + window)
    start = max(0, end - window)
    return slice(start, end)


def estimate_gravity_vector(
    df: pd.DataFrame,
    min_window_s: float = 3.0,
    sample_rate: int = 20,
) -> np.ndarray:
    """Estimate gravity from the accelerometer over a "still" window.

    Used on the **mobile / specific-force path**, where ``accel_*`` measures
    gravity plus dynamic acceleration. While the phone is rotating, ``accel_*``
    contains tangential and centripetal contributions on top of gravity. When
    angular speed is near zero and the skier is roughly stationary (chairlift
    bench, lift line, pre-run pause), accelerometer magnitude collapses to
    pure gravity, and its direction in the sensor frame is exactly what we
    need to build a body-frame rotation.

    The window-finding logic is shared with the Gravity.csv branch in
    ``align_session`` via ``_find_still_window_slice`` so both paths consume
    the same definition of "still". On the Sensor Logger path the helper is
    used directly against ``gravity_*``; this function is the path for inputs
    where no separate gravity stream exists.

    Algorithm (delegated to ``_find_still_window_slice``):

    1. Compute a rolling minimum of ``gyro_mag`` over a window of
       ``min_window_s * sample_rate`` samples.
    2. Find the index where that rolling minimum is smallest, the end of the
       calmest contiguous window in the session.
    3. Take ``min_window_s * sample_rate`` samples centered on that index
       (clamped to DataFrame bounds) and return the per-axis mean of
       ``accel_x``, ``accel_y``, ``accel_z`` over that slice.

    Fallback: when ``gyro_mag`` is missing, the DataFrame is shorter than the
    window, or the rolling minimum is all-NaN, the helper returns the full
    DataFrame slice and this function returns the mean of the entire
    accelerometer columns. Strictly worse than a real still window, but keeps
    the pipeline running on degenerate inputs.

    Parameters
    ----------
    df : pandas.DataFrame
        Preprocessed session DataFrame, expected to contain ``accel_x``,
        ``accel_y``, ``accel_z`` (and ideally ``gyro_mag``).
    min_window_s : float
        Length in seconds of the still-window the estimator looks for.
        3 seconds at 20 Hz averages 60 samples, which suppresses gyro
        noise without requiring a long pause.
    sample_rate : int
        Sample rate in Hz of the (already-downsampled) DataFrame.

    Returns
    -------
    numpy.ndarray
        Shape ``(3,)``, dtype float64. The estimated gravity vector in the
        sensor frame, in m/s². Magnitude should be close to 9.81 when the
        algorithm found a real still window.
    """
    accel_cols = ["accel_x", "accel_y", "accel_z"]
    sl = _find_still_window_slice(df, min_window_s, sample_rate)
    return df.iloc[sl][accel_cols].mean().to_numpy(dtype=np.float64)


def build_rotation_matrix(g_sensor: np.ndarray) -> np.ndarray:
    """Build the rotation matrix that maps gravity in the sensor frame onto ``-z``.

    Why ``[0, 0, -1]``? Gravity points *down* (toward Earth's center). We want
    the body-frame ``+z`` axis to point *up* (anti-parallel to gravity), so
    that yaw is rotation about the vertical. Aligning the measured gravity
    vector to ``[0, 0, -1]`` in the body frame achieves exactly that:
    ``R @ g_sensor`` ends up along ``-z`` with magnitude ≈ 9.81 m/s².

    Why Rodrigues' formula? It is the closed-form rotation matrix for an
    arbitrary axis-angle pair, with no quaternions, no singularities away
    from the special cases handled below, and no scipy dependency.

    Special cases:

    * If ``g_sensor`` is already aligned with ``-z`` (or numerically very
      close), the cross-product axis has near-zero norm. The function
      returns the identity matrix.
    * If ``g_sensor`` is anti-aligned (pointing along ``+z``), the
      cross-product is also zero. We return a 180° rotation about ``x``
      (``diag(1, -1, -1)``), which maps ``+z`` to ``-z``. Any 180° axis in
      the ``xy`` plane would work; ``x`` is a fixed, deterministic choice.

    Parameters
    ----------
    g_sensor : numpy.ndarray
        Gravity vector in the sensor frame, shape ``(3,)``. Magnitude
        should be ≈ 9.81 m/s²; only direction is used here, magnitude is
        normalized away.

    Returns
    -------
    numpy.ndarray
        Shape ``(3, 3)``, dtype float64. Rotation matrix ``R`` such that
        ``R @ g_sensor / ||g_sensor|| ≈ [0, 0, -1]``.
    """
    g = np.asarray(g_sensor, dtype=np.float64).reshape(3)
    norm = np.linalg.norm(g)
    if norm < 1e-12:
        return np.eye(3, dtype=np.float64)

    g_hat = g / norm

    axis = np.cross(g_hat, _TARGET_DOWN)
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm < 1e-6:
        dot = float(np.dot(g_hat, _TARGET_DOWN))
        if dot > 1.0 - 1e-9:
            return np.eye(3, dtype=np.float64)
        if dot < -1.0 + 1e-9:
            return np.array(
                [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]],
                dtype=np.float64,
            )
        return np.eye(3, dtype=np.float64)

    k = axis / axis_norm

    cos_theta = float(np.clip(np.dot(g_hat, _TARGET_DOWN), -1.0, 1.0))
    sin_theta = float(np.sqrt(max(0.0, 1.0 - cos_theta * cos_theta)))

    K = np.array(
        [
            [0.0, -k[2], k[1]],
            [k[2], 0.0, -k[0]],
            [-k[1], k[0], 0.0],
        ],
        dtype=np.float64,
    )

    R = (
        np.eye(3, dtype=np.float64) * cos_theta
        + (1.0 - cos_theta) * np.outer(k, k)
        + sin_theta * K
    )
    return R


def apply_frame_alignment(
    df: pd.DataFrame,
    R: np.ndarray,
    accel_includes_gravity: bool = True,
) -> pd.DataFrame:
    """Rotate ``accel_*`` and ``gyro_*`` from sensor to body frame.

    Two input conventions are supported via ``accel_includes_gravity``:

    * **True (mobile / specific-force input)**: the accelerometer carries
      gravity *plus* linear acceleration, e.g. ``expo-sensors``
      ``Accelerometer`` on iOS. After rotating into the body frame, gravity
      is a constant ``[0, 0, -9.81]`` baseline; this function subtracts it
      so the resulting ``accel_*`` columns hold true dynamic acceleration,
      which is what every centripetal-force argument and every g-force
      metric in the pipeline actually wants.
    * **False (Sensor Logger iOS / gravity-compensated input)**: the input
      ``accel_*`` is already linear-only (``CMDeviceMotion.userAcceleration``
      written into ``Accelerometer.csv``); gravity lives in a separate
      ``Gravity.csv`` stream. There is no baseline to subtract, so the
      rotated values are written back as-is.

    Gyroscope readings are angular velocity in the sensor frame; rotating
    them by ``R`` re-expresses them in the body frame. There is no constant
    component to subtract: a still phone reads ``[0, 0, 0]`` on the gyro
    regardless of orientation, and this is independent of which accel
    convention the input uses.

    The magnitudes ``accel_mag`` and ``gyro_mag`` are recomputed from the
    rotated (and, when applicable, gravity-compensated) values so downstream
    code consuming those magnitudes sees consistent numbers.

    All other columns in ``df`` are passed through untouched.

    Parameters
    ----------
    df : pandas.DataFrame
        Preprocessed session DataFrame containing ``accel_x``, ``accel_y``,
        ``accel_z``, ``gyro_x``, ``gyro_y``, ``gyro_z``, ``accel_mag``,
        ``gyro_mag``.
    R : numpy.ndarray
        Shape ``(3, 3)``. Sensor-to-body rotation, e.g. from
        ``build_rotation_matrix``.
    accel_includes_gravity : bool, default True
        Whether the input accelerometer carries gravity (specific force,
        mobile path) or is already gravity-compensated (Sensor Logger
        ``userAcceleration`` path).

    Returns
    -------
    pandas.DataFrame
        New DataFrame (a copy) with the six axis columns and the two
        magnitude columns rewritten in body frame. Column order and all
        other columns are preserved.
    """
    df = df.copy()
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)

    accel_sensor = df[["accel_x", "accel_y", "accel_z"]].to_numpy(dtype=np.float64)
    gyro_sensor = df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=np.float64)

    accel_body = accel_sensor @ R.T
    gyro_body = gyro_sensor @ R.T

    if accel_includes_gravity:
        body_gravity = np.array([0.0, 0.0, -_GRAVITY_M_S2], dtype=np.float64)
        accel_out = accel_body - body_gravity
    else:
        accel_out = accel_body

    df["accel_x"] = accel_out[:, 0]
    df["accel_y"] = accel_out[:, 1]
    df["accel_z"] = accel_out[:, 2]

    df["gyro_x"] = gyro_body[:, 0]
    df["gyro_y"] = gyro_body[:, 1]
    df["gyro_z"] = gyro_body[:, 2]

    df["accel_mag"] = np.sqrt(np.sum(accel_out * accel_out, axis=1))
    df["gyro_mag"] = np.sqrt(np.sum(gyro_body * gyro_body, axis=1))

    return df


def align_session(
    df: pd.DataFrame,
    sample_rate: int = 20,
    phone_placement: str = "unknown",
) -> pd.DataFrame:
    """End-to-end static gravity alignment for one session.

    Composes the building blocks: locate the calmest window, source a
    gravity vector for that window, build the rotation that sends gravity
    onto ``-z``, apply that rotation (and, when appropriate, the body-frame
    gravity subtraction) to the IMU columns. Adds a boolean
    ``frame_aligned`` column so downstream consumers can verify the data is
    in body frame and not sensor frame.

    ``phone_placement`` is read off the mobile recorder's
    ``session_metadata.json`` (e.g. ``"femur"``, ``"chest"``, or
    ``"unknown"`` when missing). It is currently informational only — the
    rotation logic is identical for every placement — and is logged at
    INFO so a downstream phase can confirm the wiring before plumbing
    placement-conditional behavior through this module.

    Two paths, picked automatically based on what the loader already merged
    into the DataFrame:

    * **Gravity.csv path (Sensor Logger iOS)**: when ``gravity_x``,
      ``gravity_y``, ``gravity_z`` columns are all present, gravity is read
      directly from that dedicated stream, averaged over the still window
      shared with ``estimate_gravity_vector`` via
      ``_find_still_window_slice``. ``Accelerometer.csv`` from Sensor Logger
      is ``userAcceleration`` (already gravity-compensated), so
      ``accel_includes_gravity=False`` and no gravity baseline is subtracted
      after rotation.
    * **Accelerometer path (mobile)**: when no ``gravity_*`` stream exists,
      gravity is inferred from ``accel_*`` over the still window via
      ``estimate_gravity_vector``. The mobile ``expo-sensors``
      ``Accelerometer`` reports specific force, so
      ``accel_includes_gravity=True`` and the constant ``[0, 0, -9.81]``
      baseline is subtracted in the body frame.

    Both paths share ``_find_still_window_slice``, so they pick the same
    rows of the session as "still". The magnitude check at the end is
    valid for both paths: Core Motion's gravity stream and a real
    still-window accelerometer estimate should each have magnitude close
    to 9.81 m/s². When the measured magnitude is far from 1 g the
    alignment is unreliable but still applied: the pipeline is more useful
    with a degraded body frame than with the raw tilted sensor frame, and
    the warning gives users a chance to discard the session at the report
    stage.

    Parameters
    ----------
    df : pandas.DataFrame
        Preprocessed session DataFrame, post-``compute_row_features``.
        May optionally contain ``gravity_x/y/z`` columns from
        ``Gravity.csv``.
    sample_rate : int
        Sample rate of the DataFrame in Hz. Threaded into the still-window
        helper used by both paths.
    phone_placement : str, default ``"unknown"``
        Where the phone was carried during the recording (``"femur"``,
        ``"chest"``, ``"unknown"``). Logged at INFO; not yet used to alter
        the rotation logic.

    Returns
    -------
    pandas.DataFrame
        New DataFrame in body frame, with ``frame_aligned=True`` added.
    """
    logger.info("Frame alignment: phone_placement=%s", phone_placement)

    grav_cols = ["gravity_x", "gravity_y", "gravity_z"]
    if all(c in df.columns for c in grav_cols):
        sl = _find_still_window_slice(df, min_window_s=3.0, sample_rate=sample_rate)
        g_vec = df.iloc[sl][grav_cols].mean().to_numpy(dtype=np.float64)
        accel_includes_gravity = False
    else:
        g_vec = estimate_gravity_vector(df, sample_rate=sample_rate)
        accel_includes_gravity = True

    still_quality = float(np.linalg.norm(g_vec) / _GRAVITY_M_S2)
    if not (0.85 <= still_quality <= 1.15):
        logger.warning(
            "Frame alignment: gravity estimate magnitude {:.3f}g — session may "
            "have no still window; alignment quality degraded.".format(still_quality)
        )

    R = build_rotation_matrix(g_vec)
    df = apply_frame_alignment(df, R, accel_includes_gravity=accel_includes_gravity)
    df["frame_aligned"] = True
    return df
