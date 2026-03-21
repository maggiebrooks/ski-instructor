# ski-ai Mathematical Reference

This document defines every physics-based and derived metric in the
pipeline. Each entry includes its equation, variables, physical source,
assumptions, failure modes, and confidence interpretation.

Metrics are classified as:

- **PHYSICS-DERIVED** -- grounded in classical mechanics; high confidence
  when sensor inputs are clean.
- **HEURISTIC / ESTIMATED** -- reasonable proxies that lack a direct
  physical measurement; inherently lower confidence.

---

## 1. Speed

**Category:** PHYSICS-DERIVED (sensor-reported)

**Definition:** Instantaneous ground speed of the skier as reported by
the GPS receiver.

**Equation:**

\[
v = v_{\text{GPS}}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(v\) | Ground speed | m/s |
| \(v_{\text{GPS}}\) | GPS-reported speed | m/s |

**Source:** GPS Doppler velocity measurement. Modern smartphone GPS
chipsets derive speed from carrier-phase Doppler shift, which is
typically more accurate than differentiating position fixes.

**Assumptions:**
- GPS receiver reports instantaneous ground speed, not position-derived
  speed.
- Smartphone GPS operates at ~1 Hz; values between fixes are
  interpolated by `merge_asof` during ingestion.

**Failure Modes:**
- Tree cover, canyons, or indoor segments degrade GPS accuracy.
- Cold starts or weak satellite geometry increase error.
- Speed is ground-plane projected; on steep slopes, true velocity
  along the slope is higher by a factor of \(1 / \cos(\alpha)\) where
  \(\alpha\) is the slope angle.

**Confidence Interpretation:**
- High when `horizontalAccuracy` < 10 m and speed > 1 m/s.
- Low when GPS accuracy is poor or the skier is stationary.

---

## 2. Angular Velocity

**Category:** PHYSICS-DERIVED (direct measurement)

**Definition:** Rate of rotation about the vertical (yaw) axis as
measured by the gyroscope z-axis.

**Equation:**

\[
\omega = \text{gyro}_z
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(\omega\) | Angular velocity about the yaw axis | rad/s |
| \(\text{gyro}_z\) | Gyroscope z-axis reading | rad/s |

**Source:** Direct MEMS gyroscope measurement. The z-axis of the
phone mounted on the pelvis (belly pocket) approximates the
body's yaw rotation axis during skiing.

**Assumptions:**
- Phone orientation is approximately stable in the pocket, with the
  z-axis aligned to the gravitational vertical.
- Gyroscope bias drift is negligible over the duration of a single
  turn (~1-3 seconds).

**Failure Modes:**
- Phone rotation within the pocket misaligns the z-axis.
- Gyroscope saturation at very high angular rates (typically > 35 rad/s
  on modern phones; well above skiing rates).
- Bias drift accumulates in long integrations but is acceptable for
  per-turn measurements.

**Confidence Interpretation:**
- High when \(|\omega| > 0.3\) rad/s (clear rotational signal).
- Low when \(|\omega| < 0.1\) rad/s (signal approaches noise floor).

---

## 3. Turn Radius

**Category:** PHYSICS-DERIVED

**Definition:** Estimated radius of curvature of the skier's path at
the apex of the turn, derived from instantaneous circular motion.

**Equation:**

\[
r = \frac{v}{\omega}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(r\) | Turn radius | m |
| \(v\) | Speed at apex | m/s |
| \(\omega\) | Peak angular velocity (absolute) | rad/s |

**Source:** Circular motion kinematics. For an object moving in a
circular arc, \(v = \omega \cdot r\). Rearranging gives the radius.

**Assumptions:**
- The skier follows an instantaneously circular arc at the turn apex.
- Speed and angular velocity are measured simultaneously at the peak.
- The yaw-axis gyroscope reading corresponds to the turning rate in the
  ground plane.

**Failure Modes:**
- **Low \(\omega\):** When \(\omega < 0.1\) rad/s, the denominator
  approaches zero and the radius diverges. The pipeline guards this
  by returning `None` when \(\omega < 0.1\) or \(v < 1.0\) m/s.
- **Non-circular paths:** Skidded turns, hockey stops, and S-curves
  violate the circular arc assumption.
- **GPS-gyro timing mismatch:** GPS updates at ~1 Hz while gyro runs
  at 100 Hz. Speed at the exact apex moment is interpolated.

**Confidence Interpretation:**
- High when \(\omega > 0.5\) rad/s and speed > 5 m/s.
- Moderate when \(0.1 < \omega < 0.5\) rad/s.
- `None` (not computed) when guards trigger.

---

## 4. Centripetal Acceleration (expected)

**Category:** PHYSICS-DERIVED

**Definition:** The lateral acceleration that a perfectly circular arc
at the measured speed and radius would produce.

**Equation:**

\[
a_c = \frac{v^2}{r}
\]

Or equivalently, substituting \(r = v / \omega\):

\[
a_c = v \cdot \omega
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(a_c\) | Centripetal acceleration | m/s\(^2\) |
| \(v\) | Speed at apex | m/s |
| \(r\) | Turn radius | m |

**Source:** Newton's second law applied to circular motion
(\(F_c = m \cdot a_c = m \cdot v^2 / r\)).

**Assumptions:**
- Same as Turn Radius: instantaneous circular motion at the apex.
- No lateral sliding (pure carving).

**Failure Modes:**
- Inherits all failure modes from Turn Radius.
- When radius is very small (tight turn at high speed), expected
  acceleration becomes unrealistically large.

**Confidence Interpretation:**
- Confidence equals the minimum of speed confidence and radius
  confidence.

---

## 5. Pressure Proxy (Pressure Ratio)

**Category:** PHYSICS-DERIVED

**Definition:** Ratio of measured acceleration to the centripetal
acceleration expected from pure circular motion. Indicates how
efficiently the skier loads the ski.

**Equation:**

\[
\text{pressure\_ratio} = \frac{g_{\text{measured}}}{g_{\text{expected}}}
= \frac{g_{\text{measured}}}{v^2 / (r \cdot 9.81)}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(g_{\text{measured}}\) | Peak acceleration magnitude / 9.807 | g |
| \(g_{\text{expected}}\) | \(v^2 / (r \cdot 9.81)\) | g |
| \(v\) | Speed at apex | m/s |
| \(r\) | Turn radius | m |

**Source:** Comparison of measured forces against Newtonian
prediction for uniform circular motion.

**Assumptions:**
- Circular arc at the apex.
- Accelerometer reading after gravity removal reflects lateral
  (centripetal) loading.
- The phone's accelerometer measures the sum of all non-gravitational
  forces, not just the centripetal component.

**Failure Modes:**
- Accelerometer measures total body acceleration including vertical
  bouncing, fore-aft braking, and vibration -- not purely centripetal.
- Ratios diverge when \(r < 0.5\) m (guard applied) or \(v \approx 0\).
- Values > 1 may indicate aggressive loading or measurement noise,
  not a physics violation.

**Confidence Interpretation:**
- Compounds turn radius and speed confidence.
- Additional penalty when radius < 2 m or speed < 3 m/s.

**Interpretation scale:**
- ~1.0: efficient carving (measured force matches expected centripetal).
- < 0.6: likely skidding or light pressure.
- \> 1.2: aggressive loading or noisy accelerometer.

---

## 6. Turn Angle

**Category:** PHYSICS-DERIVED

**Definition:** Total angular displacement during a turn, computed by
integrating the yaw-axis angular velocity over the turn duration.

**Equation:**

\[
\theta = \int_{t_0}^{t_1} \omega(t) \, dt
\]

Computed via the trapezoidal rule (`scipy.integrate.trapezoid`).

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(\theta\) | Integrated turn angle | rad (displayed as degrees) |
| \(\omega(t)\) | Instantaneous angular velocity | rad/s |
| \(t_0, t_1\) | Turn start and end times | s |

**Source:** Kinematic definition of angular displacement as the
integral of angular velocity.

**Assumptions:**
- The gyroscope z-axis is aligned with the vertical rotation axis.
- Turn boundaries (start/end) are correctly identified by the
  segmentation algorithm (midpoints between detected peaks).
- Gyroscope bias is negligible over the turn duration.

**Failure Modes:**
- Accumulated gyro drift in very long turns (> 5 s).
- Incorrect turn boundaries can include partial adjacent turns.
- Trapezoidal integration introduces discretization error proportional
  to the square of the sample interval (\(O(h^2)\)).

**Confidence Interpretation:**
- High when sampling rate is stable and turn duration is 0.5-5 s.
- Lower for very short turns (few samples) or very long turns
  (drift accumulation).

---

## 7. Turn Symmetry

**Category:** HEURISTIC

**Definition:** Temporal symmetry of the turn, measured as how close
the peak angular velocity occurs to the temporal midpoint of the turn.

**Equation:**

\[
\text{symmetry} = \max\!\left(0,\; 1 - \frac{|t_{\text{peak}} - t_{\text{mid}}|}{T / 2}\right)
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(t_{\text{peak}}\) | Time of peak angular velocity | s |
| \(t_{\text{mid}}\) | Midpoint time of the turn | s |
| \(T\) | Turn duration | s |

**Source:** Heuristic proxy for biomechanical turn symmetry. A
symmetric turn has its apex (peak angular rate) at the temporal
center. PSIA teaching emphasizes symmetrical weight transfer
through the turn phases.

**Assumptions:**
- Peak angular velocity is a meaningful proxy for the turn apex.
- Temporal centering of the apex indicates balanced initiation
  and completion phases.

**Failure Modes:**
- Asymmetric terrain (e.g., variable pitch) naturally shifts the
  apex without indicating poor technique.
- Very short turns have few samples, making the ratio noisy.
- The metric does not capture spatial symmetry (left vs. right
  arc shape), only temporal symmetry.

**Confidence Interpretation:**
- Moderate baseline (heuristic metric).
- Lower for turns shorter than 0.5 s.

---

## 8. Edge Angle (Roll Range)

**Category:** HEURISTIC / ESTIMATED

**Definition:** Estimated range of edge engagement during a turn,
derived from the maximum-minus-minimum roll angle reported by the
phone's orientation sensor.

**Equation:**

\[
\text{edge\_range} = \text{roll}_{\max} - \text{roll}_{\min}
\]

(Converted from radians to degrees for display.)

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(\text{roll}_{\max}\) | Maximum roll angle in the turn | rad |
| \(\text{roll}_{\min}\) | Minimum roll angle in the turn | rad |

**Source:** Heuristic. The phone's roll angle in the pocket
correlates with, but does not directly measure, the ski's edge
angle. True edge angle requires a boot-mounted sensor.

**Assumptions:**
- The phone remains in a consistent pocket orientation.
- Roll variation during a turn primarily reflects lateral body
  inclination, which correlates with edge angle.
- The relationship between body roll and ski edge angle is
  approximately linear for moderate angles.

**Failure Modes:**
- Phone movement in pocket introduces roll artifacts.
- At high edge angles (> 60 deg), the correlation between body
  roll and ski edge angle becomes nonlinear.
- This is NOT a direct edge angle measurement. It is an estimate.

**Confidence Interpretation:**
- Always lower than physics-derived metrics.
- Baseline confidence ~0.5, reflecting the indirect measurement.

---

## 9. Turn Rhythm

**Category:** HEURISTIC

**Definition:** Consistency of turn timing across a session, measured
as one minus the coefficient of variation of turn durations.

**Equation:**

\[
\text{rhythm} = 1 - \text{CV}(T_1, T_2, \ldots, T_n)
= 1 - \frac{\sigma_T}{\bar{T}}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(\sigma_T\) | Standard deviation of turn durations | s |
| \(\bar{T}\) | Mean turn duration | s |
| \(n\) | Number of turns | -- |

**Source:** Coaching heuristic. PSIA emphasizes rhythmic turn
execution as an indicator of flow and control. Consistent cadence
suggests the skier is actively managing turn initiation.

**Assumptions:**
- All turns in the session are comparable (same terrain type).
- Variation in turn duration reflects technique, not terrain changes.

**Failure Modes:**
- Mixed terrain (groomers + moguls) inflates CV and artificially
  reduces the rhythm score.
- Very few turns (< 5) make CV unreliable.

**Confidence Interpretation:**
- Requires at least 5 turns (pipeline minimum).
- Higher confidence with more turns and consistent terrain.

---

## 10. Speed Loss Ratio

**Category:** PHYSICS-DERIVED

**Definition:** Fractional speed lost during a turn, measured from
turn initiation to turn finish.

**Equation:**

\[
\text{speed\_loss} = \frac{v_{\text{init}} - v_{\text{finish}}}{v_{\text{init}}}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(v_{\text{init}}\) | Speed at turn initiation | m/s |
| \(v_{\text{finish}}\) | Speed at turn finish | m/s |

**Source:** Energy dissipation during a turn. In a perfectly carved
turn on a frictionless surface, speed would increase (gravity).
Speed loss indicates energy dissipation through skidding, snow
friction, or air resistance.

**Assumptions:**
- Speed measurements at initiation and finish are accurate.
- The turn boundaries (initiation/finish from phase detection) are
  correctly placed.

**Failure Modes:**
- Returns `None` when \(v_{\text{init}} < 1.0\) m/s (guard).
- On steep terrain, gravity acceleration can mask friction losses,
  producing negative speed loss (speed gain through the turn).
- GPS speed at 1 Hz may not capture the exact initiation/finish
  moments.

**Confidence Interpretation:**
- High when both initiation and finish speeds are > 3 m/s.
- Lower when either speed is near the guard threshold.

---

## 11. Torso Rotation Ratio

**Category:** PHYSICS-DERIVED

**Definition:** Ratio of estimated upper-body rotation to the
ski's arc angle, indicating how much the torso steers versus how
much the edges carve.

**Equation:**

\[
\text{torso\_ratio} = \frac{\omega_{\text{peak}} \cdot T}{|\theta|}
\]

**Variables:**

| Symbol | Description | Units |
|--------|-------------|-------|
| \(\omega_{\text{peak}}\) | Peak angular velocity | rad/s |
| \(T\) | Turn duration | s |
| \(\theta\) | Integrated turn angle | deg |

**Source:** Biomechanical proxy. In an edge-driven (carved) turn,
the skis follow an arc and the torso stays quiet (low ratio).
In a steering-driven turn, the torso rotates to guide the skis
(high ratio).

**Assumptions:**
- \(\omega_{\text{peak}} \cdot T\) approximates total torso rotation
  (rectangular integration upper bound).
- Turn angle \(\theta\) represents the ski's arc.

**Failure Modes:**
- The rectangular approximation overestimates actual rotation.
- When \(\theta \approx 0\), the ratio diverges (guarded).

**Confidence Interpretation:**
- Inherits confidence from turn angle and angular velocity.
- Lower when turn angle < 10 degrees.

**Interpretation scale:**
- < 0.3: quiet upper body (edge-driven).
- 0.3-0.7: moderate rotary input.
- \> 0.7: steering-driven turns.

---

## Guard Conditions Summary

The pipeline applies guards to prevent numerically unstable results:

| Metric | Guard | Result when triggered |
|--------|-------|----------------------|
| Turn radius | \(\omega < 0.1\) rad/s or \(v < 1.0\) m/s | `None` |
| Pressure ratio | \(r < 0.5\) m | `NaN` (excluded from median) |
| Speed loss | \(v_{\text{init}} < 1.0\) m/s | `None` |
| Torso rotation | \(\theta = 0\) | `NaN` (excluded from median) |
| Radius stability | Valid samples < 3 | `None` |
| All session scores | Total turns < 5 | All scores `None` |

---

## Confidence Model

Each metric receives a confidence score in \([0, 1]\) based on:

1. **Sensor quality:** GPS accuracy, sampling rate stability.
2. **Signal strength:** Magnitude of the primary input signal
   (e.g., low \(\omega\) reduces radius confidence).
3. **Numerical stability:** Proximity to guard thresholds.
4. **Metric category:** Physics-derived metrics start at a higher
   baseline than heuristics.

See `ski/analysis/confidence.py` for the implementation.
