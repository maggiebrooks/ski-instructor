# ski-ai Algorithm Specification

*Living document. Last updated: April 2026.*

This is the **assumptions ledger** for the ski-ai pipeline. Every
coordinate frame, sample rate, filter cutoff, segmentation threshold,
turn-detection parameter, and "good"-threshold zone in the code is
recorded here with its current value, source justification, and
planned change.

If you change a number in the code, update the matching row here in
the same commit. If you cannot, the change should be rejected in code
review.

This document is the **training spec** for next winter's on-snow
validation. The intentional-error session (10 runs with deliberate
backseat / banking / skidding) targets the rows tagged
`validation_status: proxy` or `validation_status: empirical`.

Companion documents:

- [research/literature-synthesis.md](research/literature-synthesis.md) —
  the academic basis for every "source" cell.
- [research/algorithm-implications.md](research/algorithm-implications.md) —
  the engineering rationale for every "decision" cell.

---

## 1. Coordinate frames

### 1.1 Sensor frame (input)

| Field | Value |
|-------|-------|
| Source | iPhone built-in IMU, exported by Sensor Logger as Accelerometer.csv, Gyroscope.csv, Orientation.csv |
| Definition | Apple Core Motion device-fixed axes: +x = right of screen, +y = top of screen, +z = out of screen toward user |
| Sample rate | 100 Hz (accel, gyro), variable for secondary sensors |
| Mounting assumption | Phone in **front thigh pocket** (preferred), screen toward body, top of phone roughly upward (see `docs/MASTER_PLAN.md` Phone placement spec) |
| Validation status | empirical, untested per-session |

### 1.2 Body frame (intermediate, **not yet implemented**)

| Field | Value |
|-------|-------|
| Source | Planned: gravity vector (vertical) + GPS bearing (heading) at session start |
| Definition | Z-axis = −gravity (up); X-axis = projected GPS heading; Y = Z × X |
| Validation status | future-work; tracked in `algorithm-implications.md` Section 2 |
| Planned location | `ski/processing/frame_alignment.py` |

### 1.3 World frame (target)

| Field | Value |
|-------|-------|
| Convention | X = east, Y = north, Z = up (matches Tang 2024) |
| Status | future-work; not used by any current metric |

### 1.4 Where we currently use raw sensor-frame values without transformation

| Quantity | File | Line | Treated as |
|----------|------|-----:|------------|
| `gyro_z` | [transformations/process_session.py](../transformations/process_session.py) | 288 | Turn axis (true world-vertical only when phone Z ≈ vertical) |
| `gyro_z` integration | [features/modules/pelvis_turn_module.py](../features/modules/pelvis_turn_module.py) | 26 | Turn angle in radians |
| `accel_mag` | [features/modules/pelvis_turn_module.py](../features/modules/pelvis_turn_module.py) | 43 | Centripetal magnitude (only valid if pocket motion is dominated by lateral skiing forces) |
| `roll` (Sensor Logger fused) | [features/modules/pelvis_turn_module.py](../features/modules/pelvis_turn_module.py) | 40 | Edge angle proxy (only valid if Sensor Logger's roll axis aligns with ski edge) |
| `speed` (GPS) | [features/modules/pelvis_turn_module.py](../features/modules/pelvis_turn_module.py) | 31 | Apex linear speed (m/s) |

Each of these will be revisited once Section 1.2 lands.

---

## 2. Pipeline parameters

| Name | Current value | File | Line(s) | Source / justification | Planned change |
|------|--------------:|------|--------:|------------------------|----------------|
| Butterworth low-pass cutoff `cutoff` | 5 Hz | `transformations/process_session.py` | 159 | Elfmark 2021 explicitly uses 4th-order zero-phase Butterworth at fc = 5 Hz on position before differentiation | none (fc) |
| Butterworth filter order `order` | 4 | `transformations/process_session.py` | 159 | Elfmark 2021 — 4th-order zero-phase Butterworth at fc = 5 Hz before differentiation | none (shipped) |
| Down-sample target rate `target_hz` | 20 Hz | `transformations/process_session.py` | 159 | Madgwick 2010 reports < 2° static and < 7° dynamic error even at 10 Hz update rate; 20 Hz is comfortably safe | none |
| Source IMU rate `source_hz` | 100 Hz | `transformations/process_session.py` | 159 | Sensor Logger native rate | none |
| `segment_runs.window_s` | 30 s | `transformations/process_session.py` | 221 | empirical (large enough to smooth barometric noise, small enough to catch chairlift transitions) | none until labelled-run study |
| `segment_runs.descent_thresh` | −0.3 m/s | `transformations/process_session.py` | 221 | empirical | none until labelled-run study |
| `segment_runs.ascent_thresh` | +0.3 m/s | `transformations/process_session.py` | 221 | empirical | none until labelled-run study |
| `segment_runs.min_segment_s` | 30 s | `transformations/process_session.py` | 221 | empirical (absorbs short flickers) | none until labelled-run study |
| `detect_turns.height` | 0.5 rad/s | `transformations/process_session.py` | 288 | empirical, on raw `\|gyro_z\|` in tilted phone frame | recalibrate after Section 1.2 frame alignment lands |
| `detect_turns.distance` | 20 samples (1 s @ 20 Hz) | `transformations/process_session.py` | 288 | empirical (rules out double-counting of one turn) | none |
| Min turns for movement scores `MIN_TURNS_FOR_SCORES` | 5 | `ski/analysis/turn_insights.py` | 35 | empirical; below this, CV / median estimates are too noisy | revisit if jack-knife noise study suggests a higher floor |
| Centripetal radius safe-floor `safe_radius` | 0.5 m | `ski/analysis/turn_insights.py` | 288 | empirical (avoids divide-by-zero and degenerate apex turns) | none |
| Carving phase signal floor (gyro / speed) | gyro > 0.1 rad/s, speed > 1.0 m/s | `features/modules/carving_phase_module.py` | 80 | empirical | none |

---

## 3. "Good" thresholds (semantic zones)

These are the human-meaning bands attached to dimensionless metrics.
Every band below is **unvalidated** until the on-snow intentional-error
session runs next winter.

### 3.1 Pressure ratio (centripetal physics)

| Zone | Range | Source | Validation status |
|------|-------|--------|--------------------|
| Skidded | < 0.6 | docstring guidance, [ski/analysis/turn_insights.py](../ski/analysis/turn_insights.py) line 254 | proxy — **invented cutoff**; replace with physics-derived bound (see below) |
| Efficient carving | 0.8 – 1.2 | docstring guidance, same line | proxy — **invented band**; should become a tolerance around unity |
| Aggressive / overloaded | > 1.2 | docstring guidance, same line | proxy — **invented cutoff**; justify vs. noise + `accel_mag` ≠ lateral |

`pressure_ratio = median(measured_g / (v² / r · g))` over a session.
Defined at [ski/analysis/turn_insights.py L283-L296](../ski/analysis/turn_insights.py).

**Physics anchor (before next winter, desk work).** Centripetal
acceleration is \(a_c = v^2/r\); in units of \(g\),
\(g_{\text{expected}} = v^2/(r g_0)\) with \(g_0 = 9.81\) m/s² — the
same formula as `expected_g` in code. For a carved arc with consistent
\(v\) and \(r\), an ideal **lateral** specific force at the apex matches
that value, so **pressure ratio → 1** is the natural centre (not 0.8
or 1.2 as magic anchors). Example: \(v = 10\) m/s, \(r = 10\) m →
\(a_c = 10\) m/s² → \(g_{\text{expected}} \approx 1.02\,g\).

**Skidding and the sign of `pressure_ratio` (not obvious).** One
story: less lateral specific force than the kinematic \(v^2/r\)
demands → **ratio < 1**. Another story: a skidded path can follow a
**larger effective turn radius** than the radius encoded in the
denominator. Our denominator uses `pelvis_estimated_turn_radius`
(\(r \approx v/\omega\) at the apex from the pocket IMU), which is
neither the ski-path radius nor the CoM radius from Adelsberger 2014.
If skidding makes that estimate **too small** vs. the radius that
would match the actual lateral load, then `expected_g` is **too
large** and the ratio is **suppressed**; if the estimate is **too
large**, `expected_g` is **too small** and the ratio **inflates**
— so **ratio > 1** is possible under skid-like mechanics even when
the docstring labels **< 0.6 as "skidding"**. Until the desk pass
characterises \(r\) vs. load on labelled runs, treat **both**
directions as physically plausible and do not treat the current zone
labels as causal truth. Full discussion:
[research/algorithm-implications.md §6](research/algorithm-implications.md).

### 3.2 Torso rotation ratio

| Zone | Range | Source | Validation status |
|------|-------|--------|--------------------|
| Stable upper body (edge-driven) | < 0.3 | docstring guidance, [ski/analysis/turn_insights.py](../ski/analysis/turn_insights.py) line 256 | proxy |
| Mixed | 0.3 – 0.7 | implicit | proxy |
| Upper-body steering | > 0.7 | docstring guidance, same line | proxy |

`torso_rotation_ratio = median((ang_vel · duration) / |turn_angle|)`.
Defined at [ski/analysis/turn_insights.py L298-L308](../ski/analysis/turn_insights.py).

### 3.3 Edge build progressiveness (`pelvis_edge_build_progressiveness`)

| Field | Value |
|-------|-------|
| Definition | Absolute slope of fused `roll` vs. time from **initiation** to **apex** (linear `polyfit` on that phase), reported as \(|d\,\mathrm{roll}/dt|\) in **deg/s** (see [features/modules/carving_phase_module.py](../features/modules/carving_phase_module.py) `compute_carving_metrics`, lines 66–75). |
| Stored name | `pelvis_edge_build_progressiveness` on turns / DB (from [CarvingPhaseModule](../features/modules/carving_phase_module.py) `pelvis_edge_build_progressiveness` key). |
| Used in | `edge_consistency` in [ski/analysis/turn_insights.py L413-L426](../ski/analysis/turn_insights.py) — median across turns is passed through `clip(..., 0, 1)`. Typical values are **tens of deg/s**, so this term **saturates at 1.0** for almost all real turns unless rescaled. |
| Literature | None in the nine-paper corpus; Reid/Komissarov-style edge-angle concepts (cited in Tang 2024) are not this exact signal. |
| Validation status | **proxy** — coaching intuition ("progressive edge build") without external validation or consistent scaling to [0, 1]. |

### 3.4 Movement score clipping ranges

All six scores are clipped to [0, 1] after composition. Their
ingredient-level clipping appears in `compute_movement_scores`:

| Score | Composition | Clipping locations |
|-------|------------|--------------------|
| `rotary_stability` | `1 − clip(torso_rotation_ratio, 0, 1)` | [ski/analysis/turn_insights.py L408-L411](../ski/analysis/turn_insights.py) |
| `edge_consistency` | mean of `1 − clip(radius_cv)`, `clip(edge_progressiveness)`, `1 − clip(radius_stability)` | [ski/analysis/turn_insights.py L413-L426](../ski/analysis/turn_insights.py) |
| `pressure_management` | `clip(pressure_ratio)` (or fallback `clip(g_force/1.2)`), combined with `1 − clip(speed_loss)` | [ski/analysis/turn_insights.py L428-L446](../ski/analysis/turn_insights.py) |
| `turn_symmetry` | mean of `1 − clip(\|L−R\|/total)`, `clip(symmetry)`, `1 − clip(\|L_radius − R_radius\|/avg_radius)` | [ski/analysis/turn_insights.py L448-L467](../ski/analysis/turn_insights.py) |
| `turn_shape_consistency` | mean of `1 − clip(radius_cv)`, `1 − clip(angle_cv)` | [ski/analysis/turn_insights.py L469-L478](../ski/analysis/turn_insights.py) |
| `turn_rhythm` | `1 − clip(duration_cv)` | [ski/analysis/turn_insights.py L480-L491](../ski/analysis/turn_insights.py) |

The pressure-management `1.2 g` fallback ceiling at line 438 is a
**hard-coded heuristic** equivalent to "1.2 g is a strong
recreational turn"; it is the legacy ceiling used when `pressure_ratio`
cannot be computed (e.g., missing GPS speed). It is included in the
proxy classification.

### 3.5 Coaching action map

Prescriptive coaching strings live in `METRIC_ACTION_MAP` at
[ski/analysis/turn_insights.py L48-L71](../ski/analysis/turn_insights.py).
Tag: editorial; not a measurement threshold.

---

## 4. Known limitations and explicit non-claims

These are statements the system is *not* allowed to make in any UI
copy, marketing material, or report header until validated.

| Non-claim | Reason | Reference |
|-----------|--------|-----------|
| "Measured ski edge angle" | Roll is taken from Sensor Logger's fused IMU and assumed to track ski edge. We have no ski IMU. | Tang 2024 reports γ RMSE 13° even with a ski-mounted IMU. |
| "Centre-of-mass trajectory" | We use the phone's location (thigh pocket, near pelvis) as a proxy. Fasel 2016 measures hip-to-CoM offset at ~0.10 m. | Fasel 2016 |
| "Carving vs. skidding detection" (binary) | `pressure_ratio` is a single-IMU proxy with no ground-truth calibration. The literature gold standard requires strain gauges + dGNSS. | Adelsberger 2014 |
| "Sub-metre turn radius accuracy" | Even strain-gauge + dGNSS pipelines report ~1 m RMS difference between ski and CoM radius. | Adelsberger 2014 |
| "Sub-degree edge or attitude accuracy" | Single-phone fusion + tilted pocket frame cannot reach Madgwick's lab-validated < 0.6° static error. | Madgwick 2010 |
| "GPS-tracked race line" | BFU 2025 measures consumer phone GNSS at ~4.5 m mean horizontal error. | BFU 2025 |
| "Real-time on-snow feedback" | Pipeline is batch-processing. | Architecture |

When the on-snow validation produces evidence sufficient to retire any
of these non-claims, that row moves into Section 3 with a measured
threshold and a named validation event.

---

## 5. Validation status legend

| Tag | Meaning |
|-----|---------|
| `validated` | Backed by a published reference or our own labelled measurement. |
| `empirical` | Tuned by hand on the three logged sessions; works for them, may not generalise. |
| `proxy` | A surrogate metric for something the literature measures with better instruments. We can compute it; we cannot defend its absolute accuracy. |
| `future-work` | Planned but not yet in the code. |

The default for every parameter introduced from now on is `empirical`.
A row is promoted to `validated` only after a documented validation
event (see Section 6) and a measured noise band.

---

## 6. Planned validation events

| Event | When | Targets |
|-------|------|---------|
| **Desk physics pass** — \(g_{\text{expected}} = v^2/(r g_0)\) grid, unity anchor, tolerance bands, `accel_mag` vs. lateral caveat | Before next winter (rainy-afternoon scope) | Section 3.1: replace invented 0.6 / 0.8 / 1.2 with derived numbers + documented assumptions; see [research/algorithm-implications.md §6](research/algorithm-implications.md) |
| Frame-alignment landing | Six-month window (before next winter) | Sections 1.2, 1.3; recalibrates 1.4 entries |
| 4th-order Butterworth at fc = 5 Hz in `preprocess()` | **Done** (shipped with this parameter set) | Section 2 row `order` = 4; regression = `pytest tests/` |
| Intentional-error on-snow session (10 runs: backseat, banking, skidding, plus baseline) | Next winter (Dec 2026 / Jan 2027) | **Tunes** Section 3.1–3.4 after the desk pass; separates error categories from baseline; cannot be the first time thresholds meet \(F=mv^2/r\) |
| Repeat-skier longitudinal study | After ≥ 5 users with ≥ 3 sessions each | `MIN_TURNS_FOR_SCORES`, jack-knife uncertainty bands |

The **desk physics pass** is mandatory before treating on-snow results
as meaningful for `pressure_ratio`: it moves the zones from invented
numbers to a tolerance around unity. The intentional-error session
then converts physics-anchored proxy bands into **validated** bands
with measured separation; it is also the main path to retire rows in
Section 4 once evidence exists.

---

## 7. How to update this document

Every PR that:

1. Adds, removes, or changes a numeric parameter, OR
2. Adds, removes, or changes a coordinate transform, OR
3. Adds, removes, or changes a "good" / "bad" threshold zone, OR
4. Adds or removes any user-facing claim about accuracy

**must** update the matching row in this document in the same commit.
If a parameter is being added, also create its row in Section 2 or
Section 3 with `validation_status: empirical` (or `proxy`) until a
validation event proves otherwise. If a non-claim is being retired,
move it from Section 4 to Section 3 with the validation event cited.

A single-line addition to the PR template (`Updated docs/algorithm-spec.md? [yes/no/N/A]`) is sufficient to enforce
this without ceremony.
