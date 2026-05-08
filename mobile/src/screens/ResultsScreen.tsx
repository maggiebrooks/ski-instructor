import { useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import BigButton from '../components/BigButton';
import { deleteSession, getSession, type SessionReport, type SessionStatusResponse } from '../lib/api';
import { sessionQualityTier, type SessionQualityFile } from '../lib/csv';
import type { Go } from '../navigation';
import { colors, radii, spacing, typography } from '../theme';

type Props = { go: Go; sessionId: string };

const POLL_MS = 2000;
const MAX_CONSECUTIVE_FAILURES = 8;

export default function ResultsScreen({ go, sessionId }: Props) {
  const [data, setData] = useState<SessionStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollFailures, setPollFailures] = useState(0);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await getSession(sessionId);
        if (cancelled) return;
        setData(res);
        setPollFailures(0);
        if (res.status === 'complete' || res.status === 'error') {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
        }
      } catch (e) {
        if (cancelled) return;
        setPollFailures((n) => n + 1);
        if (pollFailures + 1 >= MAX_CONSECUTIVE_FAILURES) {
          setError(e instanceof Error ? e.message : String(e));
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    }

    setError(null);
    setData(null);
    setPollFailures(0);
    void poll();
    timerRef.current = setInterval(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const status = data?.status ?? 'processing';
  const progress = data?.progress ?? 'upload_received';
  const report: SessionReport | null = data?.report ?? null;

  const topInsight = report?.top_insight?.trim() || null;
  const scores = report?.scores ?? null;
  const insights = (report?.insights ?? []).filter((s) => s.trim().length > 0);
  const warnings = (report?.warnings ?? []).filter((s) => s.trim().length > 0);

  const averageScore = useMemo(() => {
    if (!scores) return null;
    const vals = Object.values(scores).filter((v): v is number => v != null);
    if (vals.length === 0) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }, [scores]);

  const hasAnyNonNullScore = Boolean(
    scores && Object.values(scores).some((v) => v != null),
  );
  const scoreConfidence = report?.score_confidence;
  const filteredTurnCount = report?.filtered_turn_count;
  const showLowDataCallout =
    scoreConfidence === 'low' ||
    (typeof filteredTurnCount === 'number' && filteredTurnCount < 5);
  const showLimitedDataNote =
    scoreConfidence === 'medium' && !showLowDataCallout;

  const handleDelete = async () => {
    if (!deleteConfirming) {
      setDeleteConfirming(true);
      return;
    }
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteSession(sessionId);
      go({ name: 'home' });
    } catch (err) {
      setDeleteError('Delete failed. Please try again.');
      setDeleteConfirming(false);
    } finally {
      setDeleteLoading(false);
    }
  };

  if (error) {
    return (
      <ScrollView contentContainerStyle={styles.root}>
        <Text style={styles.title}>Results unavailable</Text>
        <Text selectable selectionColor={colors.primary} style={styles.errText}>
          {error}
        </Text>
        <View style={{ height: spacing.lg }} />
        <BigButton label="Back to Home" variant="secondary" onPress={() => go({ name: 'home' })} />
      </ScrollView>
    );
  }

  // Backend returned an error state.
  if (status === 'error') {
    return (
      <ScrollView contentContainerStyle={styles.root}>
        <Text style={styles.title}>Processing failed</Text>
        <Text style={styles.body}>The pipeline hit an error. Try uploading again.</Text>
        {data?.error ? (
          <View style={styles.block}>
            <Text style={styles.blockTitle}>Error details</Text>
            <Text selectable selectionColor={colors.primary} style={styles.mono}>
              {data.error}
            </Text>
          </View>
        ) : null}
        <View style={{ height: spacing.lg }} />
        <BigButton label="Back" variant="secondary" onPress={() => go({ name: 'home' })} />
      </ScrollView>
    );
  }

  // Still processing.
  if (status !== 'complete') {
    return (
      <ScrollView contentContainerStyle={styles.root}>
        <Text style={styles.title}>Working on your session</Text>
        <View style={styles.block}>
          <Text style={styles.body}>Status: {status}</Text>
          <Text style={styles.body}>Stage: {progress}</Text>
          {pollFailures > 0 ? (
            <Text style={styles.muted}>
              Network hiccups: {pollFailures}/{MAX_CONSECUTIVE_FAILURES}
            </Text>
          ) : null}
        </View>
        <View style={{ height: spacing.lg }} />
        <BigButton label="Back" variant="secondary" onPress={() => go({ name: 'home' })} />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.root}>
      <Text style={styles.title}>Your results</Text>

      <View style={styles.hero}>
        <Text style={styles.heroKicker}>Top focus</Text>
        <Text style={styles.heroInsight}>
          {topInsight ?? 'Next run: focus on smooth, controlled skiing.'}
        </Text>
        <Text style={styles.muted}>
          Overall score:{' '}
          {averageScore != null ? `${(averageScore * 100).toFixed(0)}` : '--'}
        </Text>
        <View style={{ height: spacing.md }} />
        <Text style={styles.muted}>Session ID</Text>
        <Text selectable selectionColor={colors.primary} style={styles.mono}>
          {sessionId}
        </Text>
      </View>

      {report?.session_quality ? (
        <SessionSignalQualityLine quality={report.session_quality} />
      ) : null}

      {hasAnyNonNullScore && scores ? (
        <View style={styles.block}>
          <Text style={styles.blockTitle}>Movement scores</Text>
          {Object.entries(scores)
            .filter(([, v]) => v != null)
            .map(([k, v]) => (
              <View key={k} style={styles.row}>
                <Text style={styles.rowLabel}>{formatKey(k)}</Text>
                <Text style={styles.rowValue}>{((v as number) * 100).toFixed(0)}</Text>
              </View>
            ))}
        </View>
      ) : null}

      {showLimitedDataNote ? (
        <Text style={[styles.muted, styles.limitedDataNote]}>
          Scores are based on limited data; ski more runs to improve accuracy.
        </Text>
      ) : null}

      {showLowDataCallout ? (
        <View style={styles.lowDataCallout}>
          <Text style={styles.lowDataCalloutTitle}>Not enough data for scores</Text>
          <Text style={styles.lowDataCalloutBody}>
            This session had too few high-quality turns to compute movement scores.{'\n'}
            Try recording a longer run on groomed terrain.
          </Text>
        </View>
      ) : null}

      {insights.length > 0 ? (
        <View style={styles.block}>
          <Text style={styles.blockTitle}>Supporting insights</Text>
          {insights.map((s, i) => (
            <Text key={i} style={styles.bullet}>
              • {s}
            </Text>
          ))}
        </View>
      ) : null}

      {warnings.length > 0 ? (
        <View style={[styles.block, styles.warnBlock]}>
          <Text style={styles.blockTitle}>Warnings</Text>
          {warnings.map((w, i) => (
            <Text key={i} style={styles.bullet}>
              • {w}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={{ height: spacing.lg }} />
      <BigButton label="Done" variant="secondary" onPress={() => go({ name: 'home' })} />

      {deleteError && (
        <Text style={{ color: '#ff4444', textAlign: 'center', marginBottom: 8 }}>
          {deleteError}
        </Text>
      )}
      <TouchableOpacity
        onPress={handleDelete}
        disabled={deleteLoading}
        style={{
          marginTop: 16,
          paddingVertical: 12,
          paddingHorizontal: 24,
          borderRadius: 8,
          borderWidth: 1,
          borderColor: '#ff4444',
          alignItems: 'center',
          opacity: deleteLoading ? 0.5 : 1,
        }}
      >
        <Text style={{ color: '#ff4444', fontSize: 14 }}>
          {deleteLoading
            ? 'Deleting…'
            : deleteConfirming
            ? 'Tap again to confirm delete'
            : 'Delete this session'}
        </Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function SessionSignalQualityLine({ quality }: { quality: SessionQualityFile }) {
  const tier = sessionQualityTier(quality);
  const dotStyle =
    tier === 'green'
      ? styles.signalDotGood
      : tier === 'yellow'
        ? styles.signalDotFair
        : styles.signalDotWeak;
  const label =
    tier === 'green'
      ? 'Good signal quality'
      : tier === 'yellow'
        ? 'Fair signal quality'
        : 'Weak signal: results may be less accurate';
  const textStyle =
    tier === 'green'
      ? styles.signalTextGood
      : tier === 'yellow'
        ? styles.signalTextFair
        : styles.signalTextWeak;
  return (
    <View style={styles.signalQualityRow}>
      <View style={[styles.signalDot, dotStyle]} />
      <Text style={[styles.signalQualityText, textStyle]}>{label}</Text>
    </View>
  );
}

function formatKey(k: string): string {
  return k
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace('Turn', 'Turn ');
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
  body: {
    color: colors.text,
    fontSize: typography.body,
    lineHeight: 22,
  },
  muted: {
    color: colors.textMuted,
    fontSize: typography.body,
  },
  hero: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  heroKicker: {
    color: colors.textMuted,
    fontSize: typography.body,
    marginBottom: spacing.xs,
  },
  heroInsight: {
    color: colors.text,
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    lineHeight: 24,
  },
  block: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  warnBlock: {
    borderColor: colors.warning,
  },
  blockTitle: {
    color: colors.text,
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  rowLabel: {
    color: colors.textMuted,
    fontSize: typography.body,
    flexShrink: 1,
  },
  rowValue: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
    flexShrink: 0,
  },
  bullet: {
    color: colors.text,
    fontSize: typography.body,
    lineHeight: 22,
    marginBottom: spacing.xs,
  },
  errText: {
    color: colors.text,
    fontSize: typography.body,
    lineHeight: 22,
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  mono: {
    fontFamily: 'Menlo',
    color: colors.text,
    fontSize: typography.body,
    marginTop: spacing.xs,
  },
  signalQualityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  signalDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  signalDotGood: {
    backgroundColor: colors.success,
  },
  signalDotFair: {
    backgroundColor: colors.warning,
  },
  signalDotWeak: {
    backgroundColor: colors.danger,
  },
  signalQualityText: {
    flex: 1,
    fontSize: typography.body,
    lineHeight: 22,
  },
  signalTextGood: {
    color: colors.success,
  },
  signalTextFair: {
    color: colors.warning,
  },
  signalTextWeak: {
    color: colors.danger,
  },
  lowDataCallout: {
    backgroundColor: '#FFF3CD',
    borderColor: '#FFC107',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginVertical: 8,
    marginBottom: spacing.lg,
  },
  lowDataCalloutTitle: {
    color: '#5c4a00',
    fontSize: typography.bodyLarge,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  lowDataCalloutBody: {
    color: '#5c4a00',
    fontSize: typography.body,
    lineHeight: 22,
  },
  limitedDataNote: {
    marginVertical: 8,
    marginBottom: spacing.lg,
  },
});

