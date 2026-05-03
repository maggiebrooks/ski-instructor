import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import BigButton from '../components/BigButton';
import {
  sessionQualityTier,
  type SessionQualityFile,
} from '../lib/csv';
import { describeUploadError, uploadSessionZip } from '../lib/api';
import type { Go } from '../navigation';
import { colors, radii, spacing, typography } from '../theme';

type Props = {
  go: Go;
  uri: string;
  filename: string;
  sizeBytes: number;
  durationSec: number;
  accelCount: number;
  gyroCount: number;
  gpsCount: number;
  baroCount: number;
  gpsAvailable: boolean;
  sessionQuality?: SessionQualityFile;
};

type DoneInfo = { sessionId: string; duplicate: boolean };

export default function UploadScreen({
  go,
  uri,
  filename,
  sizeBytes,
  durationSec,
  accelCount,
  gyroCount,
  gpsCount,
  baroCount,
  gpsAvailable,
  sessionQuality,
}: Props) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [done, setDone] = useState<DoneInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function doUpload() {
    setError(null);
    setProgress(0);
    setUploading(true);
    try {
      const res = await uploadSessionZip(uri, filename, setProgress);
      setDone({ sessionId: res.session_id, duplicate: !!res.duplicate });
    } catch (e) {
      setError(describeUploadError(e));
    } finally {
      setUploading(false);
    }
  }

  const fromRecording = accelCount > 0 || gyroCount > 0 || durationSec > 0;
  const qualityTier =
    fromRecording && sessionQuality ? sessionQualityTier(sessionQuality) : null;
  const qualitySummary =
    fromRecording && sessionQuality
      ? `A ${sessionQuality.accel_actual_hz} Hz / G ${sessionQuality.gyro_actual_hz} Hz · drops ${(sessionQuality.accel_drop_ratio * 100).toFixed(1)}% / ${(sessionQuality.gyro_drop_ratio * 100).toFixed(1)}%`
      : null;

  return (
    <ScrollView contentContainerStyle={styles.root}>
      <Text style={styles.title}>Session ready</Text>

      <View style={styles.summary}>
        <Row label="Duration" value={fromRecording ? formatDuration(durationSec) : '— (file pick)'} />
        <Row label="Accel samples" value={fromRecording ? accelCount.toLocaleString() : '—'} />
        <Row label="Gyro samples" value={fromRecording ? gyroCount.toLocaleString() : '—'} />
        <Row label="GPS samples" value={fromRecording ? gpsCount.toLocaleString() : '—'} />
        <Row label="Baro samples" value={fromRecording ? baroCount.toLocaleString() : '—'} />
        <Row
          label="GPS available"
          value={fromRecording ? (gpsAvailable ? 'Yes' : 'No') : '—'}
        />
        <SessionQualityRow tier={qualityTier} detail={qualitySummary} />
        {qualityTier === 'red' ? (
          <Text style={styles.qualityRedNote}>
            Low sensor quality — results may be less accurate
          </Text>
        ) : null}
        <Row label="Size" value={sizeBytes ? formatSize(sizeBytes) : '—'} />
        <Row label="File" value={filename} />
      </View>

      {!done ? (
        <BigButton
          label={uploading ? `Uploading… ${(progress * 100).toFixed(0)}%` : 'Upload Session'}
          onPress={doUpload}
          loading={uploading}
          disabled={uploading}
        />
      ) : (
        <View style={styles.successBlock}>
          <Text style={styles.success}>
            {done.duplicate ? 'This session was already uploaded.' : 'Session uploaded.'}
          </Text>
          <Text style={styles.body}>Session ID</Text>
          <Text selectable selectionColor={colors.primary} style={[styles.body, styles.mono]}>
            {done.sessionId}
          </Text>
          <View style={{ height: spacing.md }} />
          <BigButton label="View Results" onPress={() => go({ name: 'results', sessionId: done.sessionId })} />
        </View>
      )}

      {error ? (
        <View style={styles.errorBlock}>
          <Text selectable selectionColor={colors.primary} style={styles.errText}>
            {error}
          </Text>
          <View style={{ height: spacing.md }} />
          <BigButton label="Try Again" onPress={doUpload} />
        </View>
      ) : null}

      <View style={{ height: spacing.lg }} />
      <BigButton
        label={done ? 'Done' : 'Cancel'}
        variant="secondary"
        onPress={() => go({ name: 'home' })}
        disabled={uploading}
      />
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

function SessionQualityRow({
  tier,
  detail,
}: {
  tier: 'green' | 'yellow' | 'red' | null;
  detail: string | null;
}) {
  const label = 'Session Quality';
  if (!tier || !detail) {
    return <Row label={label} value="—" />;
  }
  const valueColor =
    tier === 'green' ? colors.success : tier === 'yellow' ? colors.warning : colors.danger;
  const valueLabel = tier === 'green' ? 'Good' : tier === 'yellow' ? 'Fair' : 'Low';
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={{ flexShrink: 1, alignItems: 'flex-end' }}>
        <Text style={[styles.rowValue, { color: valueColor }]}>{valueLabel}</Text>
        <Text style={styles.qualityDetail} numberOfLines={3}>
          {detail}
        </Text>
      </View>
    </View>
  );
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDuration(totalSec: number): string {
  const t = Math.max(0, Math.round(totalSec));
  const m = Math.floor(t / 60);
  const s = t % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

const styles = StyleSheet.create({
  root: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xl,
  },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: '700',
    marginBottom: spacing.lg,
  },
  summary: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.lg,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: spacing.md,
  },
  rowLabel: {
    color: colors.textMuted,
    fontSize: typography.body,
    flexShrink: 0,
  },
  rowValue: {
    color: colors.text,
    fontSize: typography.body,
    fontVariant: ['tabular-nums'],
    flexShrink: 1,
    textAlign: 'right',
  },
  qualityDetail: {
    color: colors.textMuted,
    fontSize: 14,
    textAlign: 'right',
    marginTop: 4,
    lineHeight: 18,
  },
  qualityRedNote: {
    color: colors.danger,
    fontSize: typography.body,
    lineHeight: 22,
    paddingHorizontal: spacing.sm,
    paddingBottom: spacing.sm,
  },
  successBlock: {
    backgroundColor: colors.successSoft,
    borderColor: colors.success,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  success: {
    color: colors.success,
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  body: {
    color: colors.text,
    fontSize: typography.body,
    lineHeight: 22,
  },
  errorBlock: {
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  errText: {
    color: colors.text,
    fontSize: typography.body,
    lineHeight: 22,
  },
  selectable: {
    textDecorationLine: 'underline',
  },
  mono: {
    fontFamily: 'Menlo',
    fontSize: typography.body,
    color: colors.text,
  },
});
