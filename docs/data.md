# Data

## Source

We support two capture sources:

1. **Mobile app (`mobile/`)** (preferred): records exactly four sensors and uploads
   a ZIP with CSVs at the top level.
2. **Sensor Logger (iOS)** (legacy): can export many sensors; the pipeline will use
   additional CSVs when present, but the **upload contract** below is what we guarantee.

This doc is the canonical reference for **what gets uploaded** and how it’s formatted.

## Upload ZIP contents (canonical)

Required (upload validation):

- `Accelerometer.csv`
- `Gyroscope.csv`

Optional (used if present):

- `Location.csv` (GPS track; speed/bearing/accuracy)
- `Barometer.csv` (`relativeAltitude` used for lift vs skiing segmentation)

All CSVs must be at the **top level** of the ZIP (no subdirectory).

## CSV formats (mobile app + Sensor Logger compatible)

### Accelerometer.csv

- Header: `time,seconds_elapsed,x,y,z`

### Gyroscope.csv

- Header: `time,seconds_elapsed,x,y,z`

### Location.csv

- Header: `time,seconds_elapsed,latitude,longitude,altitude,speed,bearing,horizontalAccuracy,verticalAccuracy,speedAccuracy,bearingAccuracy`
- Units: speed in m/s, bearing in degrees, accuracy fields in meters
- If a field is unavailable, write `0`

### Barometer.csv

- Header: `time,seconds_elapsed,relativeAltitude,pressure`
- Units: relativeAltitude in meters (relative to session start), pressure in hPa

### Time format (all CSVs)

- `time`: Unix nanoseconds (int64). Mobile uses `Date.now() * 1e6`.
- `seconds_elapsed = (time - sessionStartTime) / 1e9`

Recorder details live in [`mobile/README.md`](../mobile/README.md).

## Processed Output Schema

After the pipeline runs, each `<session>_processed.csv` contains one row
per 50 ms (20 Hz) with these 32 columns:

| Column | Source | Description |
|--------|--------|-------------|
| `time` | Sensor Logger | Nanosecond Unix epoch (int64) |
| `accel_x`, `accel_y`, `accel_z` | Accelerometer.csv | Linear acceleration (m/s^2), LP-filtered |
| `gyro_x`, `gyro_y`, `gyro_z` | Gyroscope.csv | Angular velocity (rad/s), LP-filtered |
| `gravity_x`, `gravity_y`, `gravity_z` | Gravity.csv | Gravity vector (m/s^2), nearest-matched |
| `yaw`, `roll`, `pitch` | Orientation.csv | Device orientation (rad), nearest-matched |
| `latitude`, `longitude` | Location.csv | WGS-84 coordinates, nearest-matched |
| `altitude` | Location.csv | Ellipsoidal altitude (m) |
| `altitudeAboveMeanSeaLevel` | Location.csv | MSL altitude (m) |
| `speed` | Location.csv | Ground speed (m/s), -1 = unavailable |
| `bearing` | Location.csv | Course heading (degrees) |
| `horizontalAccuracy`, `verticalAccuracy` | Location.csv | GPS accuracy (m) |
| `pressure` | Barometer.csv | Atmospheric pressure (hPa) |
| `relativeAltitude` | Barometer.csv | Relative altitude change from session start (m) |
| `magneticBearing` | Compass.csv | Magnetic bearing (degrees), nearest-matched |
| `timestamp` | Derived | `pd.Timestamp` (UTC) from `time` |
| `seconds` | Derived | Seconds elapsed from session start (float) |
| `accel_mag` | Derived | `sqrt(accel_x^2 + accel_y^2 + accel_z^2)` |
| `gyro_mag` | Derived | `sqrt(gyro_x^2 + gyro_y^2 + gyro_z^2)` |
| `alt_rate` | Derived | Altitude rate of change over 30 s window (m/s) |
| `activity` | Derived | `skiing`, `lift`, or `idle` |
| `run_id` | Derived | Incrementing ID for skiing segments (0 = not skiing) |
| `turn_peak` | Derived | Boolean, True at detected turn peaks |
