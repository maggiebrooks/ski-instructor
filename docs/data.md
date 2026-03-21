# Data

## Source

Data is recorded using the [Sensor Logger](https://www.tszheichoi.com/sensorlogger)
iOS app (v1.52) on an iPhone 17. Each recording session produces a folder
of CSV files, one per sensor.

**Important:** The Sensor Logger Accelerometer on this device reports linear
acceleration (gravity already removed). The Gravity sensor separately
reports a constant 9.807 m/s^2 gravity vector. No gravity compensation is
needed in the pipeline.

## Available Sessions

| Session | Location | Date | Duration | Runs | Turns | Vertical | Max Speed |
|---------|----------|------|----------|------|-------|----------|-----------|
| `White_River_...02-22` | White River NF, CO | 2026-02-22 | 58.8 min | 9 | 556 | 1,693 m | 59.7 km/h |
| `White_River_...02-24` | White River NF, CO | 2026-02-24 | 4.6 hrs | 20 | 1,015 | 4,311 m | 70.5 km/h |
| `Aspen_Highlands-02-26` | Aspen Highlands, CO | 2026-02-26 | 4.8 hrs | 18 | 1,258 | 4,839 m | 69.6 km/h |

## Sensor Logger Sensor Files (per session folder)

| File | Sample Rate | Columns (after header) | Used in Pipeline |
|------|-------------|------------------------|:---:|
| `Accelerometer.csv` | 100 Hz | `time, seconds_elapsed, z, y, x` | Yes (primary) |
| `Gyroscope.csv` | 100 Hz | `time, seconds_elapsed, z, y, x` | Yes (primary) |
| `Gravity.csv` | 100 Hz | `time, seconds_elapsed, z, y, x` | Yes |
| `Orientation.csv` | 100 Hz | `time, seconds_elapsed, yaw, qx, qz, roll, qw, qy, pitch` | Yes (yaw, roll, pitch) |
| `Location.csv` | ~1 Hz | `time, seconds_elapsed, altitude, speedAccuracy, bearingAccuracy, latitude, altitudeAboveMeanSeaLevel, bearing, horizontalAccuracy, verticalAccuracy, longitude, speed` | Yes |
| `Barometer.csv` | ~1 Hz | `time, seconds_elapsed, relativeAltitude, pressure` | Yes |
| `Compass.csv` | 100 Hz | `time, seconds_elapsed, magneticBearing` | Yes |
| `Magnetometer.csv` | 100 Hz | `time, seconds_elapsed, z, y, x` | No |
| `MagnetometerUncalibrated.csv` | 100 Hz | `time, seconds_elapsed, ...` | No |
| `AccelerometerUncalibrated.csv` | 100 Hz | `time, seconds_elapsed, ...` | No |
| `GyroscopeUncalibrated.csv` | 100 Hz | `time, seconds_elapsed, ...` | No |
| `Annotation.csv` | -- | (empty for all current sessions) | No |
| `Metadata.csv` | -- | `version, device name, recording epoch time, ...` | Reference only |

**Timestamp format:** The `time` column is a nanosecond-precision Unix epoch
(e.g. `1771779780460808200`). The `seconds_elapsed` column is relative to
recording start.

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
