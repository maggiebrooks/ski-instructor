import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Animated,
  BackHandler,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Location from 'expo-location';
import { Accelerometer, Barometer, Gyroscope } from 'expo-sensors';

import BigButton from '../components/BigButton';
import {
  buildSessionZip,
  computeImuStreamStats,
  computeSparseStreamHz,
  uint8ToBase64,
  type BaroSample,
  type LocationSample,
  type Sample,
  type SessionQualityFile,
} from '../lib/csv';
import type { Go } from '../navigation';
import { colors, radii, spacing, typography } from '../theme';

type Subscription = { remove: () => void };

type Props = { go: Go };

// Polling intervals for the per-sensor stream listeners.
const IMU_INTERVAL_MS = 10; // 100 Hz; matches SensorLogger pipeline.
const BARO_INTERVAL_MS = 1000; // 1 Hz.
const UI_TICK_MS = 250;
/** Wall-clock windows for achieved IMU rate monitoring. */
const IMU_RATE_WINDOW_MS = 5000;
/** Consecutive sub-80 Hz windows before showing a rate warning. */
const LOW_HZ_STREAK_THRESHOLD = 3;
/** Minimum recording length before we skip the "short session" stop confirmation. */
const MIN_SESSION_S = 120;
/** GPS / barometer live quality polling (refs + interval). */
const GPS_BARO_QUALITY_INTERVAL_MS = 3000;
/** No GPS fix in this window → `gpsFixQuality` none. */
const GPS_RECENT_MAX_NS = 5 * 1e9;
/** No barometer sample in this window → `baroHealthy` false. */
const BARO_RECENT_MAX_NS = 3 * 1e9;
/** Horizontal accuracy above this (metres) → GPS degraded. */
const GPS_ACCURACY_GOOD_MAX_M = 20;

/**
 * Explicit state machine for the recording flow:
 *
 *   idle → requesting-permissions → ready → recording → stopping
 *        → uploading → done | error
 *
 * `stopping` covers CSV + ZIP build (synchronous, no await on the wire).
 * `uploading` is the actual upload state; this screen hands off to
 * `UploadScreen` which owns the POST progress UI, but we still surface a brief
 * spinner here while we write the ZIP to disk.
 */
type RecState =
  | 'idle'
  | 'requesting-permissions'
  | 'ready'
  | 'recording'
  | 'stopping'
  | 'error';

type PermStatus = 'granted' | 'denied' | 'undetermined';

type PermResult = {
  motion: PermStatus; // accel + gyro (single iOS prompt)
  location: PermStatus;
};

type GpsFixQuality = 'good' | 'degraded' | 'none';

export default function RecordScreen({ go }: Props) {
  const [state, setState] = useState<RecState>('idle');
  const [perms, setPerms] = useState<PermResult>({ motion: 'undetermined', location: 'undetermined' });
  const [error, setError] = useState<string | null>(null);

  const [accelCount, setAccelCount] = useState(0);
  const [gyroCount, setGyroCount] = useState(0);
  const [gpsCount, setGpsCount] = useState(0);
  const [baroCount, setBaroCount] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);
  /** Latest 5 s window: samples / 5 for each IMU stream. */
  const [runningImuHz, setRunningImuHz] = useState({ accel: 0, gyro: 0 });
  const [sensorRateWarning, setSensorRateWarning] = useState(false);
  const [gpsFixQuality, setGpsFixQuality] = useState<GpsFixQuality>('none');
  const [baroHealthy, setBaroHealthy] = useState(true);

  const accelBuf = useRef<Sample[]>([]);
  const gyroBuf = useRef<Sample[]>([]);
  const gpsBuf = useRef<LocationSample[]>([]);
  const baroBuf = useRef<BaroSample[]>([]);
  const baroBaselineRef = useRef<number | null>(null);

  const sessionStartNsRef = useRef<number | null>(null);
  const startMsRef = useRef<number | null>(null);

  const subsRef = useRef<Subscription[]>([]);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const imuRateTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const imuWindowAccelStartRef = useRef(0);
  const imuWindowGyroStartRef = useRef(0);
  const lowHzStreakRef = useRef(0);
  const gpsBaroQualityTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pulse = useRef(new Animated.Value(0)).current;

  const requestPermissions = useCallback(async () => {
    setState('requesting-permissions');
    setError(null);
    try {
      const a = await Accelerometer.requestPermissionsAsync();
      const g = await Gyroscope.requestPermissionsAsync();
      const loc = await Location.requestForegroundPermissionsAsync();
      // Barometer has no permission prompt on iOS; skip.

      const motion: PermStatus =
        a.status === 'granted' && g.status === 'granted'
          ? 'granted'
          : a.status === 'denied' || g.status === 'denied'
            ? 'denied'
            : 'undetermined';
      const location: PermStatus =
        loc.status === 'granted' ? 'granted' : loc.status === 'denied' ? 'denied' : 'undetermined';

      setPerms({ motion, location });

      if (motion === 'granted') {
        setState('ready');
      } else {
        setState('idle');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState('error');
    }
  }, []);

  // Run the permission flow once on mount.
  useEffect(() => {
    void requestPermissions();
    return () => stopAndCleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestPermissions]);

  // Pulsing red dot while recording.
  useEffect(() => {
    if (state !== 'recording') {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 600, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 600, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [state, pulse]);

  // Block back navigation during recording / stopping (Android hardware back +
  // any future programmatic back). iOS doesn't have a hardware back button,
  // but the same guard is applied to the in-screen "Back" button below.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (state === 'recording' || state === 'stopping') {
        Alert.alert(
          'Recording in progress',
          'Tap Stop Recording before leaving this screen, or the session will be lost.',
        );
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [state]);

  function stopAndCleanup() {
    for (const s of subsRef.current) {
      try {
        s.remove();
      } catch {
        // ignore
      }
    }
    subsRef.current = [];
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (imuRateTimerRef.current) {
      clearInterval(imuRateTimerRef.current);
      imuRateTimerRef.current = null;
    }
    if (gpsBaroQualityTimerRef.current) {
      clearInterval(gpsBaroQualityTimerRef.current);
      gpsBaroQualityTimerRef.current = null;
    }
    Accelerometer.removeAllListeners();
    Gyroscope.removeAllListeners();
    Barometer.removeAllListeners();
  }

  async function start() {
    if (state !== 'ready') return;
    setError(null);
    accelBuf.current = [];
    gyroBuf.current = [];
    gpsBuf.current = [];
    baroBuf.current = [];
    baroBaselineRef.current = null;
    setAccelCount(0);
    setGyroCount(0);
    setGpsCount(0);
    setBaroCount(0);
    setElapsedSec(0);
    setRunningImuHz({ accel: 0, gyro: 0 });
    setSensorRateWarning(false);
    setGpsFixQuality('none');
    setBaroHealthy(true);
    imuWindowAccelStartRef.current = 0;
    imuWindowGyroStartRef.current = 0;
    lowHzStreakRef.current = 0;

    const startMs = Date.now();
    startMsRef.current = startMs;
    sessionStartNsRef.current = startMs * 1e6;

    // --- IMU (100 Hz) ---------------------------------------------------
    Accelerometer.setUpdateInterval(IMU_INTERVAL_MS);
    Gyroscope.setUpdateInterval(IMU_INTERVAL_MS);
    const aSub = Accelerometer.addListener(({ x, y, z }) => {
      accelBuf.current.push({ time: Date.now() * 1e6, x, y, z });
    });
    const gSub = Gyroscope.addListener(({ x, y, z }) => {
      gyroBuf.current.push({ time: Date.now() * 1e6, x, y, z });
    });
    subsRef.current.push(aSub, gSub);

    // --- Barometer (1 Hz) -----------------------------------------------
    // expo-sensors `Barometer` returns `{ pressure: hPa, relativeAltitude }`.
    // `relativeAltitude` is only populated on iOS (CoreMotion); we recompute
    // a session-relative delta ourselves so the math is identical on Android
    // (which only gives raw pressure).
    Barometer.setUpdateInterval(BARO_INTERVAL_MS);
    const bSub = Barometer.addListener((reading: { pressure?: number; relativeAltitude?: number }) => {
      const pressureHpa = typeof reading.pressure === 'number' ? reading.pressure : 0;
      // iOS CoreMotion already provides relativeAltitude in metres relative to
      // first reading after start. We rebase against our own first sample so
      // it's relative to *session* start regardless of platform.
      const rawAlt =
        typeof reading.relativeAltitude === 'number' ? reading.relativeAltitude : NaN;
      if (baroBaselineRef.current === null && Number.isFinite(rawAlt)) {
        baroBaselineRef.current = rawAlt;
      }
      const baseline = baroBaselineRef.current ?? 0;
      const relAlt = Number.isFinite(rawAlt) ? rawAlt - baseline : 0;
      baroBuf.current.push({
        time: Date.now() * 1e6,
        relativeAltitude: relAlt,
        pressure: pressureHpa,
      });
    });
    subsRef.current.push(bSub);

    // --- GPS (1 Hz) -----------------------------------------------------
    if (perms.location === 'granted') {
      try {
        const locSub = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.BestForNavigation,
            timeInterval: 1000,
            distanceInterval: 0,
          },
          (loc) => {
            const c = loc.coords;
            gpsBuf.current.push({
              time: Date.now() * 1e6,
              latitude: c.latitude ?? 0,
              longitude: c.longitude ?? 0,
              altitude: typeof c.altitude === 'number' ? c.altitude : 0,
              speed: typeof c.speed === 'number' && c.speed >= 0 ? c.speed : 0,
              bearing: typeof c.heading === 'number' && c.heading >= 0 ? c.heading : 0,
              horizontalAccuracy: typeof c.accuracy === 'number' ? c.accuracy : 0,
              verticalAccuracy:
                typeof c.altitudeAccuracy === 'number' ? c.altitudeAccuracy : 0,
              speedAccuracy: 0, // expo-location does not expose this
              bearingAccuracy: 0, // expo-location does not expose this
            });
          },
        );
        subsRef.current.push(locSub);
      } catch (e) {
        // Don't fail the whole recording; just leave GPS empty.
        // eslint-disable-next-line no-console
        console.warn('watchPositionAsync failed:', e);
      }
    }

    tickRef.current = setInterval(() => {
      const t0 = startMsRef.current ?? Date.now();
      setElapsedSec(Math.floor((Date.now() - t0) / 1000));
      setAccelCount(accelBuf.current.length);
      setGyroCount(gyroBuf.current.length);
      setGpsCount(gpsBuf.current.length);
      setBaroCount(baroBuf.current.length);
    }, UI_TICK_MS);

    imuRateTimerRef.current = setInterval(() => {
      const na = accelBuf.current.length;
      const ng = gyroBuf.current.length;
      const da = na - imuWindowAccelStartRef.current;
      const dg = ng - imuWindowGyroStartRef.current;
      imuWindowAccelStartRef.current = na;
      imuWindowGyroStartRef.current = ng;
      const hzA = da / (IMU_RATE_WINDOW_MS / 1000);
      const hzG = dg / (IMU_RATE_WINDOW_MS / 1000);
      setRunningImuHz({
        accel: Math.round(hzA * 10) / 10,
        gyro: Math.round(hzG * 10) / 10,
      });
      const bad = hzA < 80 || hzG < 80;
      if (bad) {
        lowHzStreakRef.current += 1;
        if (lowHzStreakRef.current >= LOW_HZ_STREAK_THRESHOLD) {
          setSensorRateWarning(true);
        }
      } else {
        lowHzStreakRef.current = 0;
      }
    }, IMU_RATE_WINDOW_MS);

    const runGpsBaroQualityCheck = () => {
      const nowNs = Date.now() * 1e6;
      const gps = gpsBuf.current;
      if (gps.length === 0) {
        setGpsFixQuality('none');
      } else {
        const lastGps = gps[gps.length - 1];
        if (nowNs - lastGps.time > GPS_RECENT_MAX_NS) {
          setGpsFixQuality('none');
        } else if (lastGps.horizontalAccuracy > GPS_ACCURACY_GOOD_MAX_M) {
          setGpsFixQuality('degraded');
        } else {
          setGpsFixQuality('good');
        }
      }
      const baro = baroBuf.current;
      if (baro.length === 0) {
        setBaroHealthy(false);
      } else {
        const lastBaro = baro[baro.length - 1];
        setBaroHealthy(nowNs - lastBaro.time <= BARO_RECENT_MAX_NS);
      }
    };
    runGpsBaroQualityCheck();
    gpsBaroQualityTimerRef.current = setInterval(
      runGpsBaroQualityCheck,
      GPS_BARO_QUALITY_INTERVAL_MS,
    );

    setState('recording');
  }

  function onStopPressed() {
    if (state !== 'recording') return;
    const t0 = startMsRef.current ?? Date.now();
    const elapsed = Math.floor((Date.now() - t0) / 1000);
    if (elapsed < MIN_SESSION_S) {
      Alert.alert(
        'Short session',
        'Short session: you may not get scores. Keep recording?',
        [
          { text: 'Keep Recording', style: 'cancel' },
          { text: 'Stop Anyway', style: 'destructive', onPress: () => void finalizeStop() },
        ],
      );
      return;
    }
    void finalizeStop();
  }

  async function finalizeStop() {
    if (state !== 'recording') return;
    setState('stopping');
    stopAndCleanup();
    try {
      const accel = accelBuf.current.slice();
      const gyro = gyroBuf.current.slice();
      const location = gpsBuf.current.slice();
      const barometer = baroBuf.current.slice();
      setAccelCount(accel.length);
      setGyroCount(gyro.length);
      setGpsCount(location.length);
      setBaroCount(barometer.length);

      const t0 = startMsRef.current ?? Date.now();
      const sessionStartNs = sessionStartNsRef.current ?? t0 * 1e6;
      const durationSec = (Date.now() - t0) / 1000;

      if (accel.length === 0 || gyro.length === 0) {
        throw new Error(
          'No IMU samples captured. Make sure Motion & Fitness permission is granted ' +
            'and try again.',
        );
      }

      const aS = computeImuStreamStats(accel.map((s) => s.time));
      const gS = computeImuStreamStats(gyro.map((s) => s.time));
      const sessionQuality: SessionQualityFile = {
        accel_actual_hz: aS.actualHz,
        accel_drop_ratio: aS.dropRatio,
        accel_uniformity_ms: aS.uniformityMs,
        gyro_actual_hz: gS.actualHz,
        gyro_drop_ratio: gS.dropRatio,
        gyro_uniformity_ms: gS.uniformityMs,
        gps_actual_hz: computeSparseStreamHz(location.map((s) => s.time)),
        baro_actual_hz: computeSparseStreamHz(barometer.map((s) => s.time)),
      };

      const zipBytes = buildSessionZip({
        accel,
        gyro,
        location,
        barometer,
        sessionStartNs,
        sessionQuality,
      });
      const base64 = uint8ToBase64(zipBytes);

      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const filename = `session-${stamp}.zip`;
      const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory;
      if (!dir) throw new Error('No writable directory available.');
      const uri = dir + filename;
      await FileSystem.writeAsStringAsync(uri, base64, {
        encoding: FileSystem.EncodingType.Base64,
      });

      go({
        name: 'upload',
        uri,
        filename,
        sizeBytes: zipBytes.byteLength,
        durationSec,
        accelCount: accel.length,
        gyroCount: gyro.length,
        gpsCount: location.length,
        baroCount: barometer.length,
        gpsAvailable: perms.location === 'granted' && location.length > 0,
        sessionQuality,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState('error');
    }
  }

  // ------------------------------------------------------------------ render

  if (state === 'requesting-permissions') {
    return (
      <View style={styles.root}>
        <Text style={styles.title}>Requesting permissions…</Text>
        <Text style={styles.body}>
          The app needs Motion & Fitness (always) and Location (recommended) to record a session.
        </Text>
      </View>
    );
  }

  if (state === 'idle' && perms.motion !== 'granted') {
    return (
      <ScrollView contentContainerStyle={styles.root}>
        <Text style={styles.title}>Motion permission required</Text>
        <Text style={styles.body}>
          {perms.motion === 'denied'
            ? 'Motion access was denied. Open iOS Settings → Privacy & Security → Motion & Fitness → Ski Recorder, then return.'
            : 'This app needs Motion & Fitness access to record accelerometer and gyroscope data.'}
        </Text>
        <View style={{ height: spacing.lg }} />
        <BigButton label="Request Permission" onPress={requestPermissions} />
        <View style={{ height: spacing.md }} />
        <BigButton
          label="Open iOS Settings"
          variant="secondary"
          onPress={() => Linking.openSettings().catch(() => undefined)}
        />
        <View style={{ height: spacing.md }} />
        <BigButton label="Back" variant="secondary" onPress={() => go({ name: 'home' })} />
      </ScrollView>
    );
  }

  if (state === 'error') {
    return (
      <ScrollView contentContainerStyle={styles.root}>
        <Text style={styles.title}>Something went wrong</Text>
        <Text style={styles.errText}>{error ?? 'Unknown error.'}</Text>
        <View style={{ height: spacing.lg }} />
        <BigButton label="Try Again" onPress={() => setState('ready')} />
        <View style={{ height: spacing.md }} />
        <BigButton label="Back" variant="secondary" onPress={() => go({ name: 'home' })} />
      </ScrollView>
    );
  }

  const isStopping = state === 'stopping';
  const isRecording = state === 'recording';

  return (
    <View style={styles.root}>
      <View style={styles.statusBar}>
        {isRecording ? (
          <View style={styles.recRow}>
            <Animated.View
              style={[
                styles.dot,
                {
                  opacity: pulse.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0.35, 1],
                  }),
                  transform: [
                    {
                      scale: pulse.interpolate({
                        inputRange: [0, 1],
                        outputRange: [0.9, 1.15],
                      }),
                    },
                  ],
                },
              ]}
            />
            <Text style={styles.recText}>RECORDING</Text>
            <Text style={styles.timerText}>{formatTimer(elapsedSec)}</Text>
          </View>
        ) : isStopping ? (
          <Text style={styles.idleText}>Processing…</Text>
        ) : (
          <Text style={styles.idleText}>Ready</Text>
        )}
      </View>

      {perms.location !== 'granted' ? (
        <View style={styles.warnBox}>
          <Text style={styles.warnText}>
            GPS unavailable: turn detection and speed metrics will be limited. You can grant
            Location in iOS Settings and restart this screen.
          </Text>
        </View>
      ) : null}

      {isRecording && sensorRateWarning ? (
        <View style={styles.warnBox}>
          <Text style={styles.warnText}>
            Sensor rate low: move to open area or restart recording.
          </Text>
        </View>
      ) : null}

      <View style={styles.metricsBlock}>
        {isRecording ? (
          <Metric
            label="Achieved rate (~5s window)"
            value={`A ${runningImuHz.accel} Hz · G ${runningImuHz.gyro} Hz`}
          />
        ) : null}
        <Metric label="Accelerometer" value={`${accelCount.toLocaleString()} samples`} />
        <Metric label="Gyroscope" value={`${gyroCount.toLocaleString()} samples`} />
        <Metric label="GPS" value={`${gpsCount.toLocaleString()} samples`} />
        {isRecording ? <GpsFixQualityLine quality={gpsFixQuality} /> : null}
        <Metric label="Barometer" value={`${baroCount.toLocaleString()} samples`} />
        {isRecording && !baroHealthy ? (
          <View style={styles.baroWarnLine}>
            <Text style={styles.baroWarnText}>
              Barometer unavailable: chairlift detection disabled
            </Text>
          </View>
        ) : null}
        <Text style={styles.hint}>
          Target: IMU 100 Hz · GPS 1 Hz (best-for-navigation) · Barometer 1 Hz
        </Text>
      </View>

      {error ? <Text style={styles.errText}>{error}</Text> : null}

      <View style={styles.actions}>
        {isRecording ? (
          <BigButton label="Stop Recording" variant="danger" onPress={onStopPressed} />
        ) : (
          <BigButton
            label={isStopping ? 'Processing…' : 'Start Recording'}
            onPress={start}
            disabled={isStopping || state !== 'ready'}
            loading={isStopping}
          />
        )}
        <View style={{ height: spacing.md }} />
        <BigButton
          label="Back"
          variant="secondary"
          onPress={() => {
            if (isRecording || isStopping) {
              Alert.alert(
                'Recording in progress',
                'Tap Stop Recording before leaving this screen, or the session will be lost.',
              );
              return;
            }
            go({ name: 'home' });
          }}
          disabled={isRecording || isStopping}
        />
      </View>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function GpsFixQualityLine({ quality }: { quality: GpsFixQuality }) {
  const dotStyle =
    quality === 'good'
      ? styles.qualityDotGood
      : quality === 'degraded'
        ? styles.qualityDotDegraded
        : styles.qualityDotNone;
  const message =
    quality === 'good'
      ? 'GPS good'
      : quality === 'degraded'
        ? 'GPS weak: speed metrics may be less accurate'
        : 'No GPS: speed and run segmentation unavailable';
  return (
    <View style={styles.gpsQualityRow}>
      <View style={[styles.qualityDot, dotStyle]} />
      <Text
        style={
          quality === 'good'
            ? styles.gpsQualityTextGood
            : quality === 'degraded'
              ? styles.gpsQualityTextDegraded
              : styles.gpsQualityTextNone
        }
      >
        {message}
      </Text>
    </View>
  );
}

function formatTimer(totalSec: number): string {
  const mm = Math.floor(totalSec / 60).toString().padStart(2, '0');
  const ss = (totalSec % 60).toString().padStart(2, '0');
  return `${mm}:${ss}`;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.lg,
    justifyContent: 'space-between',
  },
  statusBar: {
    minHeight: 56,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.danger,
  },
  recText: {
    color: colors.danger,
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  timerText: {
    color: colors.text,
    fontSize: typography.metric,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    marginLeft: spacing.md,
  },
  idleText: {
    color: colors.textMuted,
    fontSize: typography.bodyLarge,
  },
  warnBox: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.warning,
  },
  warnText: {
    color: colors.warning,
    fontSize: typography.body,
    lineHeight: 22,
  },
  metricsBlock: {
    marginTop: spacing.lg,
    gap: spacing.sm,
  },
  gpsQualityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    marginTop: -spacing.xs,
    marginBottom: spacing.xs,
  },
  qualityDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  qualityDotGood: {
    backgroundColor: colors.success,
  },
  qualityDotDegraded: {
    backgroundColor: colors.warning,
  },
  qualityDotNone: {
    backgroundColor: colors.danger,
  },
  gpsQualityTextGood: {
    flex: 1,
    color: colors.success,
    fontSize: typography.body,
    lineHeight: 22,
  },
  gpsQualityTextDegraded: {
    flex: 1,
    color: colors.warning,
    fontSize: typography.body,
    lineHeight: 22,
  },
  gpsQualityTextNone: {
    flex: 1,
    color: colors.danger,
    fontSize: typography.body,
    lineHeight: 22,
  },
  baroWarnLine: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.warning,
  },
  baroWarnText: {
    color: colors.warning,
    fontSize: typography.body,
    lineHeight: 22,
  },
  metric: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: 56,
  },
  metricLabel: {
    color: colors.textMuted,
    fontSize: typography.bodyLarge,
  },
  metricValue: {
    color: colors.text,
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  hint: {
    color: colors.textMuted,
    fontSize: typography.body,
    marginTop: spacing.sm,
  },
  errText: {
    color: colors.danger,
    fontSize: typography.body,
    marginVertical: spacing.md,
  },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: '700',
  },
  body: {
    color: colors.text,
    fontSize: typography.body,
    marginTop: spacing.md,
    lineHeight: 22,
  },
  actions: {
    width: '100%',
  },
});
