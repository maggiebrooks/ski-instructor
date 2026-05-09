import { zipSync } from 'fflate';

/**
 * One IMU (accelerometer / gyroscope) sample.
 *
 * `time` is **nanoseconds since the Unix epoch** to match SensorLogger's
 * `time` column exactly. `seconds_elapsed` is computed against the recording's
 * `sessionStartTime` (also ns) at CSV-build time, so all four sensors share a
 * single zero.
 */
export type Sample = {
  time: number;
  x: number;
  y: number;
  z: number;
};

/** One GPS fix from `expo-location` `watchPositionAsync`. */
export type LocationSample = {
  time: number;
  latitude: number;
  longitude: number;
  /** Metres above WGS84 ellipsoid (iOS). `0` if unavailable. */
  altitude: number;
  /** m/s; `0` if unavailable. */
  speed: number;
  /** Degrees, 0–360, true heading; `0` if unavailable. */
  bearing: number;
  /** Metres; `0` if unavailable. */
  horizontalAccuracy: number;
  /** Metres; `0` if unavailable. */
  verticalAccuracy: number;
  /** m/s; `0` if unavailable. */
  speedAccuracy: number;
  /** Degrees; `0` if unavailable. */
  bearingAccuracy: number;
};

/** One barometer reading. */
export type BaroSample = {
  time: number;
  /** Metres relative to the **first** barometer reading of this session. */
  relativeAltitude: number;
  /** Atmospheric pressure in **hPa** (millibars). */
  pressure: number;
};

function fmt(v: number, digits = 6): string {
  return Number.isFinite(v) ? v.toFixed(digits) : '0';
}

function elapsed(timeNs: number, sessionStartNs: number): string {
  const sec = (timeNs - sessionStartNs) / 1e9;
  return Number.isFinite(sec) ? sec.toFixed(4) : '0';
}

/**
 * Render an IMU buffer to a SensorLogger-compatible CSV.
 *
 * Header: `time,seconds_elapsed,x,y,z`
 * `seconds_elapsed = (sample.time - sessionStartNs) / 1e9` so accelerometer,
 * gyroscope, GPS, and barometer all share the same zero.
 */
export function samplesToCsv(samples: Sample[], sessionStartNs: number): string {
  const lines: string[] = ['time,seconds_elapsed,x,y,z'];
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    lines.push(
      `${s.time},${elapsed(s.time, sessionStartNs)},${fmt(s.x)},${fmt(s.y)},${fmt(s.z)}`,
    );
  }
  lines.push('');
  return lines.join('\n');
}

/**
 * Render a GPS buffer to a SensorLogger-compatible CSV.
 *
 * Header (column order matters: the FastAPI / pandas pipeline reads by name,
 * but we keep SensorLogger's layout exactly so any future positional readers
 * also work):
 *
 *   time,seconds_elapsed,latitude,longitude,altitude,speed,bearing,
 *   horizontalAccuracy,verticalAccuracy,speedAccuracy,bearingAccuracy
 */
export function locationToCsv(samples: LocationSample[], sessionStartNs: number): string {
  const lines: string[] = [
    'time,seconds_elapsed,latitude,longitude,altitude,speed,bearing,horizontalAccuracy,verticalAccuracy,speedAccuracy,bearingAccuracy',
  ];
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    lines.push(
      [
        s.time,
        elapsed(s.time, sessionStartNs),
        fmt(s.latitude, 7),
        fmt(s.longitude, 7),
        fmt(s.altitude, 3),
        fmt(s.speed, 4),
        fmt(s.bearing, 3),
        fmt(s.horizontalAccuracy, 3),
        fmt(s.verticalAccuracy, 3),
        fmt(s.speedAccuracy, 4),
        fmt(s.bearingAccuracy, 3),
      ].join(','),
    );
  }
  lines.push('');
  return lines.join('\n');
}

/**
 * Render a barometer buffer to a SensorLogger-compatible CSV.
 *
 * Header: `time,seconds_elapsed,relativeAltitude,pressure`
 *
 * `relativeAltitude` is the column the Django pipeline's
 * `segment_runs()` keys off (skiing vs. chairlift detection). It is the
 * device's running delta from the first barometer reading of the session.
 */
export function barometerToCsv(samples: BaroSample[], sessionStartNs: number): string {
  const lines: string[] = ['time,seconds_elapsed,relativeAltitude,pressure'];
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    lines.push(
      `${s.time},${elapsed(s.time, sessionStartNs)},${fmt(s.relativeAltitude, 4)},${fmt(s.pressure, 4)}`,
    );
  }
  lines.push('');
  return lines.join('\n');
}

// CSV content is ASCII (digits / commas / dots / newlines), so a one-byte-per-
// char encoder is enough; this avoids relying on a global `TextEncoder`.
function asciiToBytes(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

/** Written to `session_quality.json` in the session ZIP (additive; backend ignores). */
export type SessionQualityFile = {
  accel_actual_hz: number;
  accel_drop_ratio: number;
  accel_uniformity_ms: number;
  gyro_actual_hz: number;
  gyro_drop_ratio: number;
  gyro_uniformity_ms: number;
  gps_actual_hz: number;
  baro_actual_hz: number;
};

const DROP_GAP_MS = 15;

/**
 * Per-IMU stream: achieved Hz from timestamp span, fraction of gaps > 15 ms,
 * sample std-dev of gap lengths in ms.
 */
export function computeImuStreamStats(timesNs: number[]): {
  actualHz: number;
  dropRatio: number;
  uniformityMs: number;
} {
  if (timesNs.length < 2) {
    return { actualHz: 0, dropRatio: 0, uniformityMs: 0 };
  }
  const sorted = [...timesNs].sort((a, b) => a - b);
  const durationS = (sorted[sorted.length - 1] - sorted[0]) / 1e9;
  const actualHz = durationS > 0 ? sorted.length / durationS : 0;

  const gapsMs: number[] = [];
  let drops = 0;
  for (let i = 1; i < sorted.length; i++) {
    const ms = (sorted[i] - sorted[i - 1]) / 1e6;
    gapsMs.push(ms);
    if (ms > DROP_GAP_MS) drops += 1;
  }
  const dropRatio = gapsMs.length > 0 ? drops / gapsMs.length : 0;
  const mean = gapsMs.reduce((a, b) => a + b, 0) / gapsMs.length;
  let sumSq = 0;
  for (const g of gapsMs) sumSq += (g - mean) ** 2;
  const uniformityMs =
    gapsMs.length > 1 ? Math.sqrt(sumSq / (gapsMs.length - 1)) : 0;

  return {
    actualHz: Math.round(actualHz * 10) / 10,
    dropRatio: Math.round(dropRatio * 10000) / 10000,
    uniformityMs: Math.round(uniformityMs * 10) / 10,
  };
}

/** Low-rate streams (GPS, baro): n / time span in seconds. */
export function computeSparseStreamHz(timesNs: number[]): number {
  if (timesNs.length < 2) return 0;
  const sorted = [...timesNs].sort((a, b) => a - b);
  const durationS = (sorted[sorted.length - 1] - sorted[0]) / 1e9;
  if (durationS <= 0) return 0;
  return Math.round((sorted.length / durationS) * 100) / 100;
}

export function buildSessionQualityJson(q: SessionQualityFile): string {
  return `${JSON.stringify(q, null, 2)}\n`;
}

/** Traffic-light tier from post-hoc IMU stats (Upload summary). */
export function sessionQualityTier(q: SessionQualityFile): 'green' | 'yellow' | 'red' {
  const red =
    q.accel_actual_hz < 80 ||
    q.gyro_actual_hz < 80 ||
    q.accel_drop_ratio > 0.1 ||
    q.gyro_drop_ratio > 0.1;
  if (red) return 'red';
  const green =
    q.accel_actual_hz >= 90 &&
    q.gyro_actual_hz >= 90 &&
    q.accel_drop_ratio < 0.05 &&
    q.gyro_drop_ratio < 0.05;
  if (green) return 'green';
  return 'yellow';
}

/** Where the user reported the phone was carried during the session. */
export type PhonePlacement = 'femur' | 'chest';

export type SessionBuffers = {
  accel: Sample[];
  gyro: Sample[];
  location: LocationSample[];
  barometer: BaroSample[];
  /** Nanoseconds since Unix epoch; captured when the user taps Start. */
  sessionStartNs: number;
  sessionQuality: SessionQualityFile;
  /** User-reported phone placement, picked on the ready screen before recording. */
  phonePlacement: PhonePlacement;
};

/**
 * Build a ZIP containing four top-level CSVs plus two metadata JSON files:
 *
 *   Accelerometer.csv      (always)
 *   Gyroscope.csv          (always)
 *   Location.csv           (only if at least one GPS fix was captured)
 *   Barometer.csv          (only if at least one barometer reading was captured)
 *   session_quality.json   (always; post-hoc IMU stats)
 *   session_metadata.json  (always; carries `phone_placement` for the pipeline)
 *
 * The FastAPI upload endpoint only requires `Accelerometer.csv` and
 * `Gyroscope.csv`; the other files are read by the pipeline if present
 * (`session_metadata.json` is consumed by `ski/processing/session_processor.py`
 * to pass `phone_placement` into `align_session` and `insert_session`).
 */
export function buildSessionZip(buffers: SessionBuffers): Uint8Array {
  const {
    accel,
    gyro,
    location,
    barometer,
    sessionStartNs,
    sessionQuality,
    phonePlacement,
  } = buffers;
  const sessionMetadata = `${JSON.stringify({ phone_placement: phonePlacement }, null, 2)}\n`;
  const files: Record<string, Uint8Array> = {
    'Accelerometer.csv': asciiToBytes(samplesToCsv(accel, sessionStartNs)),
    'Gyroscope.csv': asciiToBytes(samplesToCsv(gyro, sessionStartNs)),
    'session_quality.json': asciiToBytes(buildSessionQualityJson(sessionQuality)),
    'session_metadata.json': asciiToBytes(sessionMetadata),
  };
  if (location.length > 0) {
    files['Location.csv'] = asciiToBytes(locationToCsv(location, sessionStartNs));
  }
  if (barometer.length > 0) {
    files['Barometer.csv'] = asciiToBytes(barometerToCsv(barometer, sessionStartNs));
  }
  return zipSync(files);
}

// Hermes ships `btoa` since RN 0.74, but we encode by hand to keep this safe
// even on older runtimes. Chunked + table-driven so large ZIPs don't blow the
// JS stack.
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function uint8ToBase64(u8: Uint8Array): string {
  let out = '';
  let i = 0;
  const n = u8.length;
  for (; i + 2 < n; i += 3) {
    const b1 = u8[i];
    const b2 = u8[i + 1];
    const b3 = u8[i + 2];
    out += B64[b1 >> 2];
    out += B64[((b1 & 0x03) << 4) | (b2 >> 4)];
    out += B64[((b2 & 0x0f) << 2) | (b3 >> 6)];
    out += B64[b3 & 0x3f];
  }
  if (i < n) {
    const b1 = u8[i];
    const b2 = i + 1 < n ? u8[i + 1] : 0;
    out += B64[b1 >> 2];
    out += B64[((b1 & 0x03) << 4) | (b2 >> 4)];
    out += i + 1 < n ? B64[(b2 & 0x0f) << 2] : '=';
    out += '=';
  }
  return out;
}
