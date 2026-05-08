# Literature Synthesis: Sensor-Based Alpine Ski Analytics

*Last updated: April 2026. Source PDFs live in [research/](../../research/).*

This document is the academic foundation for the `ski-ai` algorithm. It
extracts the methods, error bounds, and coordinate-frame conventions from
nine peer-reviewed (or pre-print) papers, then synthesizes the field-level
consensus on how to measure ski technique with inertial and GNSS sensors.

The companion document
[algorithm-implications.md](algorithm-implications.md) translates these
findings into engineering decisions for our pipeline. The companion
[algorithm-spec.md](../algorithm-spec.md) records the exact assumptions
and thresholds we currently use, with citations back to the sections
below.

Audience: a sports-science / biomechanics reader. Tone: rigorous, with
units and uncertainty quoted wherever the original authors quoted them.

---

## Table of contents

1. [Fasel 2013: Lower-limb IMU validation](#1-fasel-2013--lower-limb-imu-validation)
2. [Fasel 2016: dGNSS + 7-IMU centre-of-mass kinematics](#2-fasel-2016--dgnss--7-imu-centre-of-mass-kinematics)
3. [Gilgien 2016: Ski geometry and kinetic energy in DH](#3-gilgien-2016--ski-geometry-and-kinetic-energy-in-dh)
4. [Adelsberger 2014: Ski bending characteristics in use](#4-adelsberger-2014--ski-bending-characteristics-in-use)
5. [Elfmark 2021: dGNSS + video pose for ski jumping](#5-elfmark-2021--dgnss--video-pose-for-ski-jumping)
6. [BFU 2025: Smartphone GNSS in skiing](#6-bfu-2025--smartphone-gnss-in-skiing)
7. [Madgwick 2010: Quaternion orientation filter](#7-madgwick-2010--quaternion-orientation-filter)
8. [Magelssen 2024: Reinforcement-learning vs. coach-led instruction](#8-magelssen-2024--reinforcement-learning-vs-coach-led-instruction)
9. [Tang 2024: SnowMotion 5-IMU consumer system](#9-tang-2024--snowmotion-5-imu-consumer-system)
10. [Cross-paper synthesis](#cross-paper-synthesis)
11. [Open problems and where ski-ai sits](#open-problems-and-where-ski-ai-sits)

---

## 1. Fasel 2013: Lower-limb IMU validation

**Citation.** Fasel B., Spörri J., Chardonnens J., Gilgien M., Kröll J.,
Müller E., Aminian K. (2013). *3D measurement of lower-limb kinematics
in alpine ski racing using inertial sensors.* (Conference abstract.)

**Sensor setup.** Four Physilog® IMUs on both shanks and both thighs of
six elite athletes, recording one giant-slalom turn (gate 7) on a
water-injected race course. Reference: 3D camcorder system. Sampling
rate is not stated in the extracted abstract; the full proceedings
paper reports 500 Hz.

**Method.** Sensor-fusion of 3D angular velocity and acceleration
following Dejnabadi et al. (2005). Drift correction applied per turn.
Per-turn comparison to camcorder ground truth on a course with 27 m
gate distance, 8 m offset, 26° slope, eight turns.

**Reported accuracy** (mean difference / standard deviation /
correlation):

| Segment | Accuracy | Precision | Correlation |
|---------|---------:|----------:|------------:|
| Shank inclination | 2.0° | 5.0° | 0.91 |
| Thigh inclination | 1.0° | 6.4° | 0.95 |
| Knee flexion | −1.4° | 5.5° | 0.98 |

The authors note that 3D camcorders themselves carry a knee-flexion
error of ~4° (Schiefermüller 2009), so per-segment accuracy is on the
order of a half camcorder error.

**Coordinate frames.** Not detailed in the abstract; the proceedings
paper uses ISB anatomical conventions per segment plus a global frame
defined by gravity and run direction.

**Limitations called out.** Short field test (one turn each); no
quantification of inter-day repeatability.

---

## 2. Fasel 2016: dGNSS + 7-IMU centre-of-mass kinematics

**Citation.** Fasel B., Spörri J., Gilgien M., Boffi G., Chardonnens J.,
Müller E., Aminian K. (2016). *Three-Dimensional Body and Centre of
Mass Kinematics in Alpine Ski Racing Using Differential GNSS and
Inertial Sensors.* Remote Sensing 8(8): 671.

**Sensor setup.** Seven Physilog® III IMUs at 500 Hz on left/right shank
(tibial plateau), left/right thigh, sacrum, sternum, and helmet. dGNSS
antenna on helmet at 50 Hz (G5Ant-2AT1 + Alpha-G3T, GPS+GLONASS L1/L2),
post-processed and spline-interpolated to 500 Hz. Hardware synchronisation
between IMU and GNSS. Reference: six gen-locked 50 Hz HDV cameras with
photogrammetric reconstruction error 23 ± 10 mm.

**Method.** Strapdown integration with drift correction (Favre 2006;
Dejnabadi-style 3D extension). ISB anatomical axes per segment. A
forward-kinematic (FK) chain rooted at the dGNSS antenna estimates
global position of every body landmark. A *simplified* variant uses
only the head and sternum IMU; the centre of mass is estimated from
the neck position with a fixed offset
\(d_{\text{neck}\rightarrow\text{CoM}} = [0.1,\,-0.75 \cdot d_{\text{trunk}},\,0]^\mathsf{T}\) m.
Vertical alignment uses gravity; azimuth alignment uses the hypothesis
that the mean of left and right shank A–P anatomical axes coincides
with the mean velocity direction over the run. No Kalman filter (called
out as future work).

**Reported accuracy** (medians; one GS turn, six athletes):

| Quantity | Accuracy | Precision (IQR) |
|----------|---------:|----------------:|
| GNSS antenna position | 0.04 m | 0.03 m |
| CoM position (full FK) | 0.08 m | 0.06 m |
| CoM position (simplified) | 0.12 m | 0.06 m |
| CoM speed (full FK) | 0.04 m/s (0.24 %) | 0.14 m/s (0.83 %) |
| CoM speed (simplified) | −0.01 m/s | 0.14 m/s |
| Hip position | ~0.10 m |: |
| Knee position | 0.14–0.16 m |: |
| Ankle position | 0.15–0.17 m |: |

The authors quote literature thresholds for what counts as a *meaningful*
difference: CoM speed differences of 0.5–1 m/s and CoM trajectory
differences of 0.1–0.5 m are technique-relevant; instantaneous speed
differences below 0.5 m/s may be noise.

**Coordinate frames.** Global Earth frame aligned to gravity (vertical)
via the IMUs and to mean velocity direction (azimuth) via the shanks.
Segment orientations expressed in ISB anatomical frames. Forward
kinematics chain originates at the GNSS antenna.

**Limitations called out.** Training-floor complexity of dGNSS plus
base station; arm orientation not measured; ~0.5 m/s instantaneous
oscillations in CoM speed; suggests Kalman or particle fusion and
optional consumer GNSS as future work.

---

## 3. Gilgien 2016: Ski geometry and kinetic energy in DH

**Citation.** Gilgien M., Spörri J., Kröll J., Müller E. (2016).
*Effect of ski geometry and standing height on kinetic energy:
equipment designed to reduce risk of severe traumatic injuries in
alpine downhill ski racing.* British Journal of Sports Medicine 50:
8–13.

**Sensor setup.** Two retired elite skiers, five ski prototypes, on a
World Cup downhill course. dGNSS at 50 Hz (GPS+GLONASS L1/L2,
backpack); CoM derived from a virtual-pendulum model on a digital
terrain model (DTM) of the snow surface (static dGNSS survey).
Reported system accuracy: CoM position 0.1 m; ground reaction force
±63 N; air drag ±42 N.

**Method.** Per-section kinetic-energy budget (E_KIN), instantaneous
speed, ground reaction force F_GRF, air drag F_F, and a coefficient of
friction Coeff_F derived from the kinetic model. Spatial normalisation
of time series to the gate sequence.

**Selected results.**

| Section | Median slope | Mean E_KIN | Mean speed |
|---------|-------------:|-----------:|-----------:|
| STEEP | −23° | 30.9 J/BW | 24.6 m/s |
| FLAT | −15° | 44.7 J/BW | 29.6 m/s |

Only the SKI_WLH prototype (narrower waist, lower stand height, longer)
reduced E_KIN in steep terrain, by ~3 % overall and up to 7 % at
specific gates. No effect on flat terrain. The authors translate ~3 %
E_KIN into roughly 0.5 m shorter jump and 0.02 s shorter airtime: too
small to compromise reaction time at typical 20 m look-ahead distances
(0.01–0.03 s gain).

**Coordinate frames.** Not detailed beyond a CoM in the terrain/global
DTM frame.

**Limitations called out.** Small sample (two athletes); ski-ability and
sport-attractiveness trade-offs for SKI_WLH (delayed reaction, reduced
rebound reported by athletes); calls for combined course + equipment
studies.

---

## 4. Adelsberger 2014: Ski bending characteristics in use

**Citation.** Adelsberger R., Aufdenblatten S., Gilgien M., Tröster G.
(2014). *On Bending Characteristics of Skis in Use.* Procedia
Engineering 72: 362–367.

**Sensor setup.** Thirty strain gauges (15 per ski, 1 cm gauge length,
~65 Hz). dGNSS at 50 Hz with virtual-pendulum CoM and a snow-surface
DTM (Gilgien 2012/2013), reported at CoM position 0.09 ± 0.12 m and
velocity 0.08 ± 0.19 m/s. Bending-machine reference laser at 0.5 mm.
Synchronisation via GPS time on an Android IOIO device.

**Method.** Strain → curvature → ski shape per ski. *Outer ski only*
analysed (inner ski strain too noisy). Per-turn radius compared
between (a) ski-derived curvature and (b) sliding-window radius of the
CoM trajectory (window size 9 CoM samples). Turn transitions detected
by sign change in angular velocity, with a 1-state hysteresis filter.

**Reported accuracy.** Lab shape RMS error 11 mm vs. laser. On-snow
RMS difference between ski radius and CoM radius: mean 1.26 m (or 1.20
m in another phrasing in the paper, with a best of 0.78 m). All ten
runs were below 2.3 m RMS difference in turn radius. Three of ten
recordings failed (GNSS not started, battery logging).

**Coordinate frames.** Strain gauges in ski local frame; CoM in
dGNSS/terrain frame.

**Limitations called out.** Inner ski poor signal-to-noise; hysteresis
in strain response; sync complexity; failed-run rate; quoted
ski-radius vs. CoM-radius RMS difference still > 1 m even on carved
turns, so the *agreement* between the two definitions of "turn radius"
itself has a noise floor of about a metre.

**Why this paper matters most.** This is the only paper in the corpus
that operationalises the *carving vs. skidding* distinction with on-snow
measurements: a carved turn is one where ski curvature radius ≈ CoM
trajectory radius. We cannot reproduce this with a single phone, but
the definition is the gold standard against which any single-IMU
"carving score" must eventually be calibrated.

---

## 5. Elfmark 2021: dGNSS + video pose for ski jumping

**Citation.** Elfmark O., Ettema G., Groos D., Ihlen E. A. F., Velta
R., Haugen P., Braaten S., Gilgien M. (2021). *Performance Analysis
in Ski Jumping with a Differential Global Navigation Satellite System
and Video-Based Pose Estimation.* Sensors 21: 5318.

**Sensor setup.** dGNSS at 50 Hz (G5Ant-2AT1 + Alpha-G3T, GPS+GLONASS
L1/L2); WGS84 → local Easting/vertical via Helmert transform.
Blackmagic 4K video at 60 Hz, shutter 1/1000 s, with a markerless
ConvNet pose estimator producing 16 keypoints in the 2D sagittal plane
(right-side landmarks). Sample window: 16 jumps from −5 m before
take-off to +20 m after.

**Method.** A 4th-order zero-phase Butterworth low-pass at fc = 5 Hz is
applied to position before differentiation. Velocities and
accelerations derived by central differences. Aerodynamic forces F_N,
F_D, F_L, F_f via standard equations; flight angle
\(\phi = \arctan(v_y/v_x)\) and local body-axis forces F_b, F_p.
Statistical comparison via SPM 1D t-tests at α = 0.05; mean absolute
errors (MAE) computed in 5 m bins.

**Reported accuracy.** dGNSS position ~±0.05 m (cited from Gilgien
2014). Trajectory MAE drops from ~0.10 m in the early take-off bin to
~0.02–0.04 m by 5 m past take-off. Worst velocity MAE ~0.49 m/s in
horizontal early bins; worst acceleration MAE ~2.45 m/s² in the
−5–0 m bin. Aerodynamic lift-to-drag ratio in stable phase 1.3–1.5;
drag area C_D·A 0.15–0.25 m² (ρ = 1.225 kg/m³).

**Coordinate frames.** Local frame placed at the in-run edge: x
downhill, y upward (gravity-aligned). Position rotated to a
skier-parallel frame via flight angle φ for body-axis force
decomposition. dGNSS measures the head; pose estimator estimates the
CoM, so the two disagree most in the take-off phase (the last 15 m
of in-run is grayed-out in figures).

**Limitations called out.** dGNSS not legal in competition; ski
orientation not measured by pose estimation; multi-camera and ski IMUs
suggested as extensions; angles stabilise only 5–10 m past take-off,
and aerodynamic conditions are stable for only ~20 m, creating tension
in any "stable phase" definition.

**Why this paper matters most.** It is the cleanest reference in the
corpus for *signal-processing conventions*: a 4th-order zero-phase
Butterworth at 5 Hz applied to position before differentiation, with
errors quoted by spatial bin. Our pipeline already uses 5 Hz; the order
and zero-phase choices justify our planned filter upgrade.

---

## 6. BFU 2025: Smartphone GNSS in skiing

**Citation.** Ellenberger L., Bürgi F., Gilgien M. (2025).
*Smartphone Movement Data in Skiing.* BFU report 2.556.08, building on
Petrella et al. (2025), PLOS ONE.

**Sensor setup.** Four iOS/Android smartphones (high- and low-end of
each platform) running four ski-tracking apps, compared against a dGNSS
reference (< 10 cm). Two locations: Davos and Zermatt. Phone GNSS
sampling at 1 Hz; downhill segments only; first 5 minutes of each
session excluded.

**Method.** Time-aligned Euclidean horizontal distance to reference;
3σ outlier rule; speed derived from differenced raw fixes.

**Reported accuracy.**

| Quantity | Result |
|----------|--------|
| Mean horizontal position error | ~4.5 m |
| 75th percentile | < 7 m |
| Outliers | up to 25 m, brief excursions > 100 m |
| High-end phones | ~4 m |
| Low-end phones | ~6 m |
| App effect | none significant |
| Mean speed error | < 2 km/h |
| 75th-percentile speed error | < 3.5 km/h |
| Position error at slow speeds (≤ 14 km/h) | ~3 m |
| Position error at ~50 km/h | > 5 m |
| Worst speed error | ~4.5 km/h around 65 km/h |
| Zermatt vs. Davos | +2.5 m position error (terrain/skyline) |

**Coordinate frames.** Not the focus.

**Limitations called out.** Sub-metre accuracy unattainable with
consumer GNSS in dynamic skiing; absolute position unsuitable for
trajectory or near-collision applications; app updates may silently
change smoothing; raw GNSS export required for scientific use.

**Why this paper matters most.** This is *our* deployment context. It
caps how much trust we can place in smartphone GNSS: speed is usable
at low rate (~2 km/h noise), but position is not, period. Any
metric that depends on absolute position is structurally broken on a
phone-only setup.

---

## 7. Madgwick 2010: Quaternion orientation filter

**Citation.** Madgwick S. O. H. (April 2010). *An efficient orientation
filter for inertial and inertial/magnetic sensor arrays.* University
of Bristol internal report.

**Sensor setup.** Xsens MTx IMU at 512 Hz raw log; Vicon optical
ground truth at 120 Hz. Eight test trials with peak rotation rates
110°/s to 190°/s.

**Method.** Quaternion orientation filter combining gyroscope
integration with a single gradient-descent step on the accelerometer
(IMU mode) or on accelerometer + magnetometer (MARG mode). Two
parameters: β controls the convergence of gradient descent against
gyro drift; ζ corrects gyro bias. The author derives optimal
β = 0.033 rad/s for IMU mode and β = 0.041 rad/s for MARG mode (with
a higher β = 2.5 for the first 10 s to converge from rest), and
ζ = 0 for the experimental data (no real bias) or ζ = 0.015 for a
synthetic 0.2°/s bias drifting at 0.2°/s/s.

The filter is one gradient-descent iteration per sample, costing 109
floating-point operations per update in IMU mode and 277 in MARG mode.

**Reported accuracy.**

| Mode | Static RMS | Dynamic RMS |
|------|-----------:|------------:|
| Proposed (φ roll) | 0.58° | 0.63° |
| Proposed (θ pitch) | 0.50° | 0.67° |
| Proposed (ψ yaw, MARG) | 1.07° | 1.11° |

Headline: under 0.6° static and under 0.8° dynamic RMS attitude error,
matching or exceeding a contemporary Kalman filter at a fraction of
the compute. Static vs. dynamic is split at gyroscope rate < 5°/s vs.
≥ 5°/s. Decimation analysis shows the filter is still under 2° static
and under 7° dynamic at 10 Hz update rate, so it is appropriate for
phone-class sample rates.

**Coordinate frames.** Quaternion \({}^S_E\hat{q}\) expresses Earth
relative to sensor. Earth frame defined by gravity (0,0,0,1) for the
accelerometer and a local magnetic reference (b_x, 0, b_z) for the
magnetometer. Initial alignment requires gravity calibration C_E,
magnetic calibration C_M, and sensor mounting calibration M_S, which
the author derives from a pendulum + compass + static-Kalman mean.

**Limitations called out.** Single-axis rotation protocol in
validation; not multi-axis simultaneously; magnetic distortion in real
environments; suggests dynamic β and ζ scheduling for high-noise
operation.

**Why this paper matters most.** It is the canonical reference for our
fusion target: free, open-source, run-time-efficient, and accurate
enough that we can throw away Sensor Logger's pre-fused yaw/roll/pitch
and own the orientation pipeline ourselves.

---

## 8. Magelssen 2024: Reinforcement-learning vs. coach-led instruction

**Citation.** Magelssen C., Gilgien M., Tajet S. L., Losnegard T.,
Haugen P., Reid R., Frömer R. (2024 pre-print). *Reinforcement
learning enhances training and performance in skilled alpine skiers
compared to traditional coaching instruction.* bioRxiv
2024.04.22.590558.

**Sensor setup.** No IMU or biomechanical GNSS in the analysis. Only
a wireless photocell timing system (HC Timing wiNode/wiTimer); the
section clock starts 10 m below the start; the dependent measure is
*section time* in seconds.

**Method.** N = 98 skilled racers (96 analysed) on a three-day indoor
SNØ slalom experiment. Participants randomised to one of three groups:

- *Reinforcement learning*: feedback was the section split time only.
- *Supervised, free choice*: coach-led traditional instruction.
- *Supervised, target-skill*: explicit instruction to use a
  theoretically optimal strategy ("extend + rock skis forward",
  derived from forward modelling and elite observation).

Main course: 19 stubby gates, 10 m gate distance, 1.9 m offset, 210 m
flat. Transfer course: variable offsets 2.2 / 1.7 / 1.2 m. Pre-registered
analysis. The minimal effect of interest was 0.3 s.

**Reported result.** The RL group improved section times more than the
free-choice supervised group; descriptively but not statistically more
than the target-skill supervised group. Coaches' free-choice
instruction was suboptimal in some cases.

**Limitations called out.** Indoor ice; not peer reviewed at time of
pre-print; coach-blinding limited.

**Why this paper matters most.** It does not change how we *measure*
skiing, but it does change how we *coach* through measurement: outcome
feedback (here, section time) can outperform corrective verbal
feedback for skilled athletes. For ski-ai this argues for a future
"skilled mode" that surfaces score deltas without prescriptive
instructions, alongside the existing prescriptive coaching strings.

---

## 9. Tang 2024: SnowMotion 5-IMU consumer system

**Citation.** Tang W., Suo X., Wang X., Shan B., Li L., Liu Y. (2024).
*SnowMotion: A Wearable Sensor-Based Mobile Platform for Alpine Skiing
Technique Assistance.* Sensors 24: 3975.

**Sensor setup.** Five IMUs (each accelerometer + gyroscope +
magnetometer) on a ski suit, Bluetooth-streamed to a smartphone running
a Unity-based 3D digital-human visualiser. GPS for location and
speed. 60 Hz IMU sampling; < 10 ms streaming latency. Initial T-pose
calibration with the user facing +x in world. Validated against Vicon
in lab for gliding, wedge, and carving.

**Method.** Per-IMU orientation in sensor coordinate system (SCS),
transformed to global coordinate system (GCS) via quaternion. Initial
attitude from accelerometer + magnetometer with explicit Z-Y-X Euler
sequence and quaternion multiplication \(q = q_z \otimes q_y \otimes q_x\).
Adaptive sensor fusion (ablations in Discussion). Coaching metrics:
knee flexion α, hip flexion β, edge angle γ, wedge angle ω, defined
following Reid and Komissarov.

**Reported accuracy.**

| Setup | Result |
|-------|--------|
| Pendulum tests at 0.5, 1, 2 Hz | RMSE ~10.1°–11.4° |
| Straight gliding, knee α (left) | RMSE 11.13° |
| Straight gliding, wedge ω | RMSE 10.07° |
| Carving, edge γ (left) | RMSE up to 13.13° |
| Correlation vs. Vicon | cc > 0.95 across motions |

The headline accuracy ("mean error 5.0°, RMSE under 12.5° across
typical skiing motions") is in degrees. The system is the closest
analogue in the corpus to what a consumer ski-ai product looks like.

**Coordinate frames.** Global coordinate system: X east, Y north, Z up.
Per-joint local frames defined per segment (RGB axes in their figures).

**Limitations called out.** Lab-only validation; no World Cup field
test; ablations on placement, fusion, and upper-body model in the
Discussion suggest known sensitivity; no ML beyond initial calibration.

**Why this paper matters most.** Sets the consumer-grade benchmark for
a similar product class. Their per-angle RMSE of 10–13° is what we
should expect to *beat* in carefully validated single-axis metrics
(roll for edge angle), or at least match in the multi-axis case, given
that they use five IMUs to our one.

---

## Cross-paper synthesis

### Reference standards

The corpus converges on a clear hierarchy of reference quality:

| Reference | Position accuracy | Use |
|-----------|------------------:|-----|
| Vicon optical motion capture | sub-millimetre | Lab validation (Madgwick, Tang) |
| HD multi-camera photogrammetry | 23 ± 10 mm | Field validation (Fasel 2016, Fasel 2013) |
| dGNSS L1/L2 with base station | 0.04–0.10 m | Field reference for CoM (Fasel, Gilgien, Adelsberger, Elfmark) |
| Consumer single-frequency GNSS | ~4.5 m horizontal | Recreational tracking only (BFU) |

### Filter conventions

Every paper that differentiates position to get speed or acceleration
applies a low-pass first. The most explicit recipe is Elfmark 2021's
**4th-order zero-phase Butterworth at fc = 5 Hz**, which suppresses
the 100 Hz IMU and 50 Hz dGNSS noise without distorting the 1–3 Hz
turn rhythm or 0.5–2 Hz pendulum-scale CoM motion. Tang 2024
implicitly relies on its 60 Hz IMU stream and adaptive fusion with no
explicit cutoff.

### Sensor-fusion methods

| Method | Static accuracy | Dynamic accuracy | Compute |
|--------|----------------:|-----------------:|---------|
| Madgwick gradient-descent | < 0.6° | < 0.8° | 109–277 ops/update |
| Strapdown + per-turn drift correction (Fasel) | not separately reported | 1–6° per segment | high (FK chain) |
| Adaptive complementary fusion (Tang) | not separately reported | 5–12° per joint | unspecified |
| Apple Core Motion (Sensor Logger source) | not published | not published, but CMDeviceMotion is widely accepted as ~1° static | unknown |

The relevant takeaway: at static or near-static rates, every modern
fusion approach reaches single-degree accuracy. The dynamic accuracy
ceiling is set by the *coordinate-frame discipline* and by the
magnetometer environment, not by the fusion algorithm itself.

### Coordinate-frame conventions

| Domain | Convention |
|--------|------------|
| Body segments | ISB anatomical axes per segment (Fasel 2013, Fasel 2016) |
| World frame | X-east, Y-north, Z-up (Tang 2024); or downhill-x, gravity-y (Elfmark 2021) |
| Sensor frame | Manufacturer's local frame, mapped to body via T-pose (Tang) or pendulum + compass calibration (Madgwick) |
| Centre-of-mass frame | Helmet-rooted FK chain (Fasel 2016) or virtual pendulum on DTM (Gilgien, Adelsberger) |

The papers with multiple IMUs all derive a *body* frame from a
calibration pose plus the gravity vector, then chain it forward into
the world frame at run start. None of them rely on the raw sensor
frame for any technique metric.

### Carving-quality measurement

Adelsberger 2014 is the only paper that operationalises carving on
snow: a carved turn is one where the **ski-curvature radius equals
the CoM trajectory radius** within ~1 m RMS. Skidded turns produce a
larger ski radius than CoM radius (the ski is sliding sideways across
the trajectory). This requires either strain-gauged skis or
multi-IMU + dGNSS instrumentation; both are out of reach for a
phone-only product.

The literature offers two single-sensor proxies that can survive
without ski strain measurement: (a) the centripetal-pressure ratio
\(g_\text{measured} / (v^2 / r \cdot g)\), which approaches 1 for an
ideally carved turn and falls below 1 for a skidded turn, and
(b) edge-angle progressiveness: how monotonically the roll angle
builds through the initiation phase. Neither is validated in the
literature against the Adelsberger gold standard.

### Coaching effectiveness

Magelssen 2024 is the lone behavioural-science paper, and its message
for instrumentation is paradoxical: the best coaching feedback for
skilled athletes was the *least informative*: a single split time  - 
because it preserved the athlete's exploration. For an instrumented
coaching product like ski-ai, this argues for two distinct UX modes:
prescriptive corrective feedback for novices, and outcome-only metric
deltas for skilled users.

---

## Open problems and where ski-ai sits

No paper in the corpus solves the exact problem ski-ai is attempting:

- **Single belly-pocket smartphone**, no other IMU, no dGNSS, no
  external camera.
- **Recreational and intermediate skiers**, not racers, so the metrics
  must be diagnostic across ability rather than performance-optimal at
  the elite level.
- **Per-turn coaching feedback**, not aggregate speed or split times.

The closest analogues are:

| Gap | Closest paper | What we cannot inherit |
|-----|---------------|------------------------|
| Multi-IMU body-segment kinematics | Fasel 2013 / Fasel 2016 | We only have one IMU |
| Centre-of-mass trajectory | Fasel 2016 simplified 2-IMU | We need the same FK rigour with one less sensor |
| Carving vs. skidding ground truth | Adelsberger 2014 | We cannot strain-gauge skis |
| Smartphone-grade GNSS expectations | BFU 2025 | We must structurally avoid absolute position |
| Consumer-grade IMU coaching system | Tang 2024 | They use 5 IMUs; we use 1 |
| Sensor-fusion algorithm | Madgwick 2010 | Adopt directly, calibrate for our mounting |
| Signal-processing recipe | Elfmark 2021 | Adopt directly (4th-order zero-phase Butterworth, fc = 5 Hz) |
| Coaching-feedback paradigm | Magelssen 2024 | Reflect in UX design, not in pipeline |

The result is that ski-ai is novel in *configuration* (one-IMU,
phone-only, recreational coaching) but conservative in *method*: every
component below the carving-vs-skidding question can be built from the
established literature; the coaching-quality scores above that line
must be validated empirically in our own data, since no paper has
done so for our sensor count.

The next step in our six-month plan, captured in
[algorithm-implications.md](algorithm-implications.md) and
[../algorithm-spec.md](../algorithm-spec.md), is to (a) adopt every
literature-validated component as a hard requirement, (b) reduce every
*proxy* metric to a documented assumption with a planned validation
test, and (c) publish a clean assumptions ledger that next winter's
on-snow validation session can attack one row at a time.
