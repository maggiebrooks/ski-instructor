import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { AxiosError } from 'axios'
import { deleteSession, getSession } from '../api'
import DemoModeBanner from '../components/DemoModeBanner'
import TurnArcViz, { type RunResult } from '../components/TurnArcViz'

const SESSION_POLL_MAX_FAILURES_DEFAULT = 8
const SESSION_POLL_MAX_FAILURES_404 = 2
const SESSION_POLL_INTERVAL_MS = 2000

const METRIC_COACHING: Record<string, string> = {
  turn_rhythm:
    'Your turn timing is inconsistent — some turns are rushed, others too drawn out. Try counting a quiet rhythm as you ski: one for the initiation, two for the fall line, three for the finish. Consistency here will make everything else feel smoother.',
  pressure_management:
    'Drive your shins into the boot tongues earlier through the fall line and keep your hands forward — that centers you over the outside ski when it matters most.',
  edge_consistency:
    'Build edge angle progressively from initiation to the fall line — let ankles and knees tip into the hill so each turn bites in the same place.',
  rotary_stability:
    'Quiet the upper body and let your legs steer — keep shoulders facing down the hill more of the turn so rotation does not replace clean edging.',
  turn_symmetry:
    'Spend a few runs mirroring your stronger side on the weaker one — match pressure, shape, and timing left and right.',
  turn_shape_consistency:
    'Aim for a more uniform turn size — mixing very short and very long arcs on the same run makes rhythm and line harder to trust.',
  turn_efficiency:
    'Look for flow turn to turn — ease off unnecessary braking and let the ski run when the slope allows; smooth speed control reads as efficiency.',
}

const SCORE_KEYS = [
  'rotary_stability',
  'edge_consistency',
  'pressure_management',
  'turn_symmetry',
  'turn_shape_consistency',
  'turn_rhythm',
  'turn_efficiency',
] as const

const SCORE_LABELS: Record<(typeof SCORE_KEYS)[number], string> = {
  rotary_stability: 'Rotary Stability',
  edge_consistency: 'Edge Consistency',
  pressure_management: 'Pressure Management',
  turn_symmetry: 'Turn Symmetry',
  turn_shape_consistency: 'Turn Shape',
  turn_rhythm: 'Turn Rhythm',
  turn_efficiency: 'Turn Efficiency',
}

const SCORE_DESCRIPTIONS: Record<(typeof SCORE_KEYS)[number], string> = {
  rotary_stability: 'How much your upper body rotates during turns. Higher is better.',
  edge_consistency:
    'How cleanly and consistently your skis grip the snow through each turn.',
  pressure_management:
    'How well you load and release the ski through the arc of the turn.',
  turn_symmetry: 'How evenly matched your left and right turns are.',
  turn_shape_consistency:
    'How consistent and round your turn arcs are from run to run.',
  turn_rhythm: 'How consistent your timing is between turns.',
  turn_efficiency:
    'How much speed you carry through turns versus scrubbing it off.',
}

/** Eventually deep-link to the iOS recorder app instead of web. */
const RECORD_NEXT_RUN_URL = 'https://ski-instructor.vercel.app'

const NEXT_RUN_FALLBACK_INSIGHT =
  'Ski another run to get your personalized focus cue.'

const METRIC_INSIGHT_HINTS: Record<(typeof SCORE_KEYS)[number], readonly string[]> = {
  rotary_stability: ['rotary', 'rotation', 'upper body', 'steering', 'shoulders', 'torso'],
  edge_consistency: ['edge', 'angles', 'tipping', 'ankles', 'knees', 'arc'],
  pressure_management: [
    'shins',
    'boots',
    'fore/aft',
    'weight is sitting',
    'outside ski',
    'decent platform',
    'solid fore',
    'ball of your foot',
    'hands forward',
    'centered over your skis',
  ],
  turn_symmetry: ['symmetry', 'left and right', 'balanced', 'weaker side', 'foot-to-foot'],
  turn_shape_consistency: ['shape', 'consistent turn', 'sharp and wide'],
  turn_rhythm: [
    'rhythm',
    'timing',
    'cadence',
    'beat',
    'spacing',
    'flow',
    'apex',
    'predictable',
    'tempo',
  ],
  turn_efficiency: ['efficien', 'skid', 'braking', 'flowing'],
}

interface SummaryBlock {
  runs?: number | null
  turns?: number | null
  vertical_m?: number | null
  max_speed_kmh?: number | null
  duration_s?: number | null
  time_skiing_s?: number | null
  time_lift_s?: number | null
  avg_run_duration_s?: number | null
  avg_turns_per_run?: number | null
  total_turns_left?: number | null
  total_turns_right?: number | null
}

interface Report {
  summary?: SummaryBlock
  scores?: Record<string, number | null>
  insights?: string[]
  warnings?: string[]
  score_confidence?: 'low' | 'medium' | 'high'
  top_insight?: string | null
  total_turn_count?: number
  filtered_turn_count?: number
  processing_version?: string
  /** Per-run turn metrics (written by worker for TurnArcViz). */
  runs?: RunResult[]
}

interface SessionData {
  session_id: string
  status: string
  progress: string
  report: Report | null
  error?: string
}

function formatSessionPollError(err: unknown): string {
  const ax = err as AxiosError<{ detail?: string }>
  if (ax.code === 'ECONNABORTED') {
    return (
      'Request timed out while checking session status. Your run may still be processing; refresh the page or open this link again in a minute.'
    )
  }
  const detail = ax.response?.data?.detail
  if (typeof detail === 'string') return `Failed to load session: ${detail}`
  if (ax.message) return `Failed to load session: ${ax.message}`
  return 'Failed to load session'
}

function humanReadableStage(progress: string): string {
  const s = progress.toLowerCase()
  if (s === 'queued') return 'Validating upload…'
  if (s === 'parsing_sensor_data' || s === 'processing') return 'Parsing sensor data…'
  if (s === 'running_pipeline') return 'Running pipeline…'
  if (s === 'generating_report' || s === 'analyzing') return 'Generating report…'
  if (s === 'generating_plots') return 'Almost done…'
  if (s === 'complete') return 'Complete.'
  return 'Processing…'
}

function extractTimestampMs(sessionId: string): number | null {
  const m13 = sessionId.match(/\d{13}/)
  if (m13) {
    const t = Number(m13[0])
    if (Number.isFinite(t)) return t
  }
  if (/^\d{10,13}$/.test(sessionId)) {
    const t = Number(sessionId)
    if (Number.isFinite(t)) return t
  }
  return null
}

function formatBreadcrumbDate(sessionId: string): string {
  const ts = extractTimestampMs(sessionId)
  if (ts == null) return 'Session'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return 'Session'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDuration(seconds: number): string {
  const totalSeconds = Math.round(seconds)
  const mins = Math.floor(totalSeconds / 60)
  const secs = totalSeconds % 60
  return `${mins}m ${secs}s`
}

function statOrDash(n: number | null | undefined, zeroAsDash = true): string {
  if (n == null) return '-'
  if (zeroAsDash && n === 0) return '-'
  return String(n)
}

function statSpeed(n: number | null | undefined): string {
  if (n == null || n === 0) return '-'
  return `${n.toFixed(1)}`
}

function statVertical(n: number | null | undefined): string {
  if (n == null || n === 0) return '-'
  return `${Math.round(n)}`
}

function statDuration(n: number | null | undefined): string {
  if (n == null || n === 0) return '-'
  return formatDuration(n)
}

function insightForMetric(
  key: (typeof SCORE_KEYS)[number],
  insights: readonly string[],
): string | null {
  const hints = METRIC_INSIGHT_HINTS[key]
  const lower = insights.map((i) => i.toLowerCase())
  for (let i = 0; i < insights.length; i++) {
    const line = lower[i] ?? ''
    if (hints.some((h) => line.includes(h))) {
      return insights[i] ?? null
    }
  }
  return null
}

function overallScoreFromReport(scores: Record<string, number | null>): number | null {
  const vals = SCORE_KEYS.map((k) => scores[k]).filter(
    (v): v is number => typeof v === 'number' && Number.isFinite(v),
  )
  if (vals.length === 0) return null
  return (vals.reduce((a, b) => a + b, 0) / vals.length) * 100
}

/** null, undefined, or non-finite → em dash; else N/100 for movement scores. */
function formatMovementScoreOutOf100(raw: number | null | undefined): string {
  if (raw === null || raw === undefined) return '—'
  if (typeof raw !== 'number' || Number.isNaN(raw) || !Number.isFinite(raw)) return '—'
  return `${Math.round(raw * 100)}/100`
}

function movementScoreFraction01(raw: number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null
  if (typeof raw !== 'number' || Number.isNaN(raw) || !Number.isFinite(raw)) return null
  return raw
}

/** null, undefined, or non-finite → em dash; else rounded percent 0–100 (no /100 suffix). */
function formatCoachScorePill01(raw: number | null | undefined): string {
  if (raw === null || raw === undefined) return '—'
  if (typeof raw !== 'number' || Number.isNaN(raw) || !Number.isFinite(raw)) return '—'
  return String(Math.round(raw * 100))
}

function scoreDisplayColor(score: number | null): string {
  if (score == null) return 'var(--color-text-muted)'
  if (score >= 70) return 'var(--color-success)'
  if (score >= 50) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

function scoreNumeric(
  scores: Record<string, number | null>,
  key: string,
): number | undefined {
  const v = scores[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

const COACHING_FRAME_LINE = 'Here is what stood out from your session:'

function splitCoachingInsights(lines: readonly string[]): {
  subtitle: string | null
  bodies: string[]
} {
  if (lines.length === 0) return { subtitle: null, bodies: [] }
  const t = lines[0].trim()
  if (
    t === COACHING_FRAME_LINE ||
    t.startsWith('Here is what stood out') ||
    t.startsWith('For your next run, focus on the following')
  ) {
    return { subtitle: lines[0].trim(), bodies: lines.slice(1) }
  }
  return { subtitle: null, bodies: [...lines] }
}

/** Order matches ``interpret_fundamentals`` in ``ski/analysis/turn_insights.py``. */
type CoachNoteCardDef = {
  label: string
  icon: string
  /** 0–1 score for left border, pill, and tier coloring. */
  tierScore: number | null
}

function coachNoteCardDefsInSessionOrder(scores: Record<string, number | null>): CoachNoteCardDef[] {
  const pm = scores.pressure_management
  const ec = scores.edge_consistency
  const out: CoachNoteCardDef[] = []
  if (pm != null) {
    out.push({ label: 'Fore/Aft Balance', icon: '⬆', tierScore: pm })
  }
  if (scores.turn_symmetry != null) {
    out.push({ label: 'Foot-to-Foot Balance', icon: '⚖', tierScore: scores.turn_symmetry })
  }
  if (scores.rotary_stability != null) {
    out.push({ label: 'Rotary Control', icon: '↻', tierScore: scores.rotary_stability })
  }
  if (ec != null) {
    out.push({ label: 'Edging Control', icon: '◇', tierScore: ec })
  }
  if (pm != null && ec != null) {
    out.push({ label: 'Pressure Control', icon: '▽', tierScore: (pm + ec) / 2 })
  } else if (pm != null) {
    out.push({ label: 'Pressure Control', icon: '▽', tierScore: pm })
  }
  if (scores.turn_rhythm != null) {
    out.push({ label: 'Turn Rhythm', icon: '∿', tierScore: scores.turn_rhythm })
  }
  return out
}

type CoachTier = 'high' | 'mid' | 'low' | 'na'

function coachScoreTier(score: number | null): CoachTier {
  if (score == null || !Number.isFinite(score)) return 'na'
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'mid'
  return 'low'
}

function coachScorePillClass(tier: CoachTier): string {
  if (tier === 'high') return 'coach-score-pill coach-score-pill--high'
  if (tier === 'mid') return 'coach-score-pill coach-score-pill--mid'
  if (tier === 'low') return 'coach-score-pill coach-score-pill--low'
  return 'coach-score-pill coach-score-pill--na'
}

function coachCardClass(tier: CoachTier): string {
  return `coach-card coach-card--${tier}`
}

function deriveAvgTurnDurationS(summary: SummaryBlock | undefined): string | null {
  if (!summary) return null
  const ard = summary.avg_run_duration_s
  const atpr = summary.avg_turns_per_run
  if (ard != null && atpr != null && atpr > 0) {
    return (ard / atpr).toFixed(1)
  }
  const dur = summary.duration_s
  const turns = summary.turns
  if (dur != null && turns != null && turns > 0) {
    return (dur / turns).toFixed(1)
  }
  return null
}

function deriveTurnsPerMinute(summary: SummaryBlock | undefined): string | null {
  if (!summary) return null
  const turns = summary.turns
  if (turns == null || turns <= 0) return null
  const ski = summary.time_skiing_s
  if (ski != null && ski > 0) {
    return (turns / (ski / 60)).toFixed(1)
  }
  const dur = summary.duration_s
  if (dur != null && dur > 0) {
    return (turns / (dur / 60)).toFixed(1)
  }
  return null
}

function buildFooterLine(report: Report): string {
  const n = report.total_turn_count
  const m = report.filtered_turn_count
  const v = report.processing_version
  if (n != null && m != null && v) {
    return `${n} turns analysed (${m} high-confidence) · v${v}`
  }
  if (n != null && m != null) {
    return `${n} turns analysed (${m} high-confidence)`
  }
  if (v) return `v${v}`
  return ''
}

function LinkCopyIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M10 13a5 5 0 0 1 5-5h1a4 4 0 0 1 4 4v4a4 4 0 0 1-4 4h-1a5 5 0 0 1-5-5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M14 11H9a4 4 0 0 0-4 4v1a4 4 0 0 0 4 4h5a4 4 0 0 0 4-4v-1a4 4 0 0 0-4-4Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StatSplitLight({
  variant,
  a,
  b,
  labelLeft,
  labelRight,
}: {
  variant: 'ski' | 'lr'
  a: number
  b: number
  labelLeft: string
  labelRight: string
}) {
  const t = a + b
  if (t <= 0) {
    return <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>-</div>
  }
  const pa = Math.round((a / t) * 1000) / 10
  const pb = 100 - pa
  const ca = variant === 'ski' ? 'stat-split-ski-a' : 'stat-split-lr-a'
  const cb = variant === 'ski' ? 'stat-split-ski-b' : 'stat-split-lr-b'
  return (
    <div className="stat-split-wrap-light">
      <div className="stat-split-bar-light">
        <div className={`stat-split-seg-light ${ca}`} style={{ width: `${pa}%` }} />
        <div className={`stat-split-seg-light ${cb}`} style={{ width: `${pb}%` }} />
      </div>
      <div className="stat-split-labels-light">
        <span>
          {labelLeft}: {Math.round(a)}
        </span>
        <span>
          {labelRight}: {Math.round(b)}
        </span>
      </div>
    </div>
  )
}

function TurnSignatureImage({ sessionId }: { sessionId: string }) {
  const src = `/api/session/${sessionId}/plot/${sessionId}_turn_signature.png`
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')

  useEffect(() => {
    setStatus('loading')
  }, [sessionId])

  return (
    <div>
      {status === 'loading' && <div className="plot-skeleton-light" aria-busy />}
      {status === 'error' && (
        <div className="plot-placeholder-light">
          Turn signature not available for this session
        </div>
      )}
      <img
        className="plot-img-light"
        src={src}
        alt="Turn analysis plot"
        style={{ display: status === 'ok' ? 'block' : 'none' }}
        onLoad={() => setStatus('ok')}
        onError={() => setStatus('error')}
      />
    </div>
  )
}

function ProcessingView({
  sessionId,
  progress,
  stageOverride,
}: {
  sessionId: string
  progress: string
  stageOverride?: string
}) {
  const stageText = stageOverride ?? humanReadableStage(progress)

  return (
    <div className="processing-light-wrap">
      <div className="processing-light-card" role="status" aria-live="polite" aria-busy="true">
        <div className="processing-light-top">
          <span className="upload-wordmark">Ski Recorder</span>
        </div>
        <div className="processing-light-id">{sessionId}</div>
        <div className="processing-indeterminate-spinner" aria-hidden />
        <p className="processing-light-stage">{stageText}</p>
        <p className="processing-light-eta">Usually takes 30–90 seconds</p>
      </div>
    </div>
  )
}

export default function Session() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const fromUpload = Boolean(
    (location.state as { fromUpload?: boolean } | null)?.fromUpload,
  )
  const [data, setData] = useState<SessionData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [copied, setCopied] = useState(false)
  const [barsReady, setBarsReady] = useState(false)
  const intervalRef = useRef<number | null>(null)
  const copyTimeoutRef = useRef<number | null>(null)
  const pollFailuresRef = useRef(0)

  useEffect(() => {
    if (!id) return
    const sessionId = id

    async function poll() {
      try {
        const res = (await getSession(sessionId)) as SessionData
        pollFailuresRef.current = 0
        setNotFound(false)
        setData(res)
        if (res.status === 'complete' || res.status === 'error') {
          if (intervalRef.current) clearInterval(intervalRef.current)
        }
      } catch (e) {
        pollFailuresRef.current += 1
        const ax = e as AxiosError<{ detail?: string }>
        const is404 = ax.response?.status === 404
        const threshold = is404
          ? SESSION_POLL_MAX_FAILURES_404
          : SESSION_POLL_MAX_FAILURES_DEFAULT
        if (pollFailuresRef.current >= threshold) {
          if (is404) {
            setNotFound(true)
            setError(null)
          } else {
            setError(formatSessionPollError(e))
          }
          if (intervalRef.current) clearInterval(intervalRef.current)
        }
      }
    }

    pollFailuresRef.current = 0
    void poll()
    intervalRef.current = window.setInterval(() => void poll(), SESSION_POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [id])

  useEffect(() => {
    setCopied(false)
    setBarsReady(false)
    if (copyTimeoutRef.current) {
      clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = null
    }
  }, [id])

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (data?.status === 'complete') {
      const t = requestAnimationFrame(() => setBarsReady(true))
      return () => cancelAnimationFrame(t)
    }
    setBarsReady(false)
    return undefined
  }, [data?.status, id])

  const handleDeleteSession = async () => {
    if (!id) return
    if (!window.confirm('Delete this session?')) return
    try {
      await deleteSession(id)
      navigate('/')
    } catch {
      setError('Failed to delete session')
    }
  }

  const copyLink = () => {
    const url = window.location.href
    void navigator.clipboard.writeText(url)
    setCopied(true)
    if (copyTimeoutRef.current) {
      clearTimeout(copyTimeoutRef.current)
    }
    copyTimeoutRef.current = window.setTimeout(() => {
      setCopied(false)
    }, 2000)
  }

  if (!id) {
    return (
      <div className="error-card-wrap">
        <div className="error-card">
          <h1>Session not found</h1>
          <p>
            This is an early preview — session data isn&apos;t persisted between server restarts.
            Upload a new session or try the sample on the home page.
          </p>
          <Link to="/" className="btn btn-primary">
            New Upload
          </Link>
        </div>
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="error-card-wrap">
        <div className="error-card">
          <h1>Session not found</h1>
          <p>
            This is an early preview — session data isn&apos;t persisted between server restarts.
            Upload a new session or try the sample on the home page.
          </p>
          <Link to="/" className="btn btn-primary">
            New Upload
          </Link>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="shell-error-generic">
        <p style={{ color: 'var(--color-danger)', marginBottom: 16 }}>{error}</p>
        <Link to="/" style={{ fontWeight: 600 }}>
          Back to upload
        </Link>
      </div>
    )
  }

  if (!data) {
    return (
      <ProcessingView
        sessionId={id}
        progress="queued"
        stageOverride={
          fromUpload ? 'Upload received. Starting analysis…' : 'Loading session…'
        }
      />
    )
  }

  if (data.status === 'error') {
    const errMsg = data.error
    return (
      <div className="shell-results">
        <h1 style={{ marginTop: 0 }}>Processing Failed</h1>
        <p style={{ color: 'var(--color-danger)' }}>
          The pipeline encountered an error. Try uploading again.
        </p>
        {errMsg && (
          <pre
            style={{
              marginTop: 16,
              padding: 14,
              background: 'var(--color-surface-raised)',
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 200,
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
            }}
          >
            {errMsg}
          </pre>
        )}
        <p style={{ marginTop: 24 }}>
          <Link to="/" style={{ fontWeight: 600 }}>
            Back to upload
          </Link>
        </p>
      </div>
    )
  }

  if (data.status !== 'complete') {
    return <ProcessingView sessionId={data.session_id} progress={data.progress} />
  }

  const report: Report = data.report ?? {}
  const scores = report.scores ?? {}
  const insights = report.insights ?? []
  const cleanedInsights = insights.filter((i: string) => i.trim().length > 0)
  const coachingParts = splitCoachingInsights(cleanedInsights)
  const coachingBodies = coachingParts.bodies
  const coachCardDefs = coachNoteCardDefsInSessionOrder(scores)
  const topInsight = report.top_insight?.trim() || null
  const warnings = report.warnings ?? []
  const scoreConfidence = report.score_confidence ?? 'unknown'
  const summary = report.summary

  const overall = overallScoreFromReport(scores)
  const allScoresNull = SCORE_KEYS.every((k) => scores[k] == null)

  const avgTurnDur = deriveAvgTurnDurationS(summary)
  const tpm = deriveTurnsPerMinute(summary)
  const skiT = summary?.time_skiing_s
  const liftT = summary?.time_lift_s
  const leftN =
    summary?.total_turns_left ?? scoreNumeric(scores, 'left_turns') ?? null
  const rightN =
    summary?.total_turns_right ?? scoreNumeric(scores, 'right_turns') ?? null

  const headline =
    topInsight || 'Next run: focus on smooth, controlled skiing and consistent turns.'

  const confidencePill =
    scoreConfidence === 'high' ? 'High confidence' : 'Limited data'

  const footerText = buildFooterLine(report)

  const runsForViz = report.runs
  const showTurnArcViz =
    Array.isArray(runsForViz) &&
    runsForViz.some((r) => Array.isArray(r.per_turn) && r.per_turn.length > 0)

  return (
    <div className="shell-results">
      <DemoModeBanner context="session" />

      <nav className="results-nav">
        <div className="results-nav-left">
          <Link to="/" style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Ski Recorder
          </Link>
          <span style={{ color: 'var(--color-text-muted)' }}> / </span>
          <span className="results-nav-crumb-strong">
            {formatBreadcrumbDate(data.session_id)}
          </span>
        </div>
        <div className="results-nav-actions">
          <button
            type="button"
            className="icon-btn-light"
            title={copied ? 'Copied' : 'Copy link'}
            aria-label={copied ? 'Link copied' : 'Copy session link'}
            onClick={copyLink}
          >
            <LinkCopyIcon />
          </button>
          <Link to="/" className="btn btn-secondary">
            New Upload
          </Link>
          <button
            type="button"
            className="results-nav-delete"
            onClick={() => void handleDeleteSession()}
          >
            Delete
          </button>
        </div>
      </nav>

      <div className="hero-race-card">
        <div className="hero-race-inner">
          <div className="hero-race-left">
            <div className="hero-race-score" style={{ color: scoreDisplayColor(overall) }}>
              {overall != null ? Math.round(overall) : '-'}
            </div>
            <div className="hero-race-score-label">Overall Score</div>
            <div className="hero-race-pill">{confidencePill}</div>
          </div>
          <div className="hero-race-divider" aria-hidden />
          <div className="hero-race-right">
            <p className="hero-race-insight">{headline}</p>
            <p className="hero-race-sub">Focus for your next run</p>
            {scoreConfidence === 'low' && (
              <div className="hero-race-warn-pill">More runs needed for full analysis</div>
            )}
          </div>
        </div>
        <div className="hero-race-stripe" aria-hidden />
      </div>

      <div className="results-columns">
        <div className="card card-hover">
          <h2 className="card-title-results">Movement Scores</h2>
          {allScoresNull && (
            <div className="banner-scores-light">
              Not enough turns for full analysis. Record a longer run on groomed terrain
            </div>
          )}
          {SCORE_KEYS.map((key, idx) => {
            const raw = scores[key]
            const n = movementScoreFraction01(raw)
            const val = n != null ? n * 100 : null
            const pct = n != null ? Math.max(0, Math.min(100, val ?? 0)) : 0
            const showTip =
              n != null && n < 0.6
                ? insightForMetric(key, coachingBodies) ?? METRIC_COACHING[key] ?? null
                : null
            const dim = n == null
            return (
              <div
                key={key}
                className={'score-row-light' + (dim ? ' score-row-light--dim' : '')}
              >
                <div className="score-row-light-head">
                  <span className="score-row-light-name">{SCORE_LABELS[key]}</span>
                  <span className="score-row-light-val">{formatMovementScoreOutOf100(raw)}</span>
                </div>
                <p className="score-row-desc">{SCORE_DESCRIPTIONS[key]}</p>
                <div className="score-bar-track-light">
                  <div
                    className="score-bar-fill-light"
                    style={{
                      width: barsReady ? `${pct}%` : '0%',
                      transitionDelay: `${idx * 100}ms`,
                    }}
                  />
                </div>
                {showTip && <p className="score-row-tip-light">{showTip}</p>}
              </div>
            )
          })}
        </div>

        <div className="card card-hover">
          <h2 className="card-title-results">Session Stats</h2>
          <div className="stats-grid-light">
            <div>
              <div className="stat-cell-value">{statOrDash(summary?.runs)}</div>
              <div className="stat-cell-label">Total Runs</div>
            </div>
            <div>
              <div className="stat-cell-value">{statOrDash(summary?.turns)}</div>
              <div className="stat-cell-label">Total Turns</div>
            </div>
            <div>
              <div className="stat-cell-value">{statVertical(summary?.vertical_m)}</div>
              <div className="stat-cell-label">Vertical Drop</div>
            </div>
            <div>
              <div className="stat-cell-value">{statSpeed(summary?.max_speed_kmh)}</div>
              <div className="stat-cell-label">Max Speed</div>
            </div>
            <div>
              <div className="stat-cell-value">{statDuration(summary?.duration_s)}</div>
              <div className="stat-cell-label">Duration</div>
            </div>
            <div>
              <div className="stat-cell-value">{tpm ?? '-'}</div>
              <div className="stat-cell-label">Turns / Min</div>
            </div>
            <div>
              <div className="stat-cell-value">{avgTurnDur ?? '-'}</div>
              <div className="stat-cell-label">Avg Turn Duration</div>
            </div>
            <div>
              <div className="stat-cell-value">
                {scores.turn_symmetry != null
                  ? `${(scores.turn_symmetry * 100).toFixed(0)}`
                  : '-'}
              </div>
              <div className="stat-cell-label">Turn Symmetry</div>
            </div>
          </div>

          {skiT != null && liftT != null && skiT + liftT > 0 && (
            <div className="stat-split-wrap-light">
              <div className="stat-split-title-light">Skiing vs Lift time</div>
              <StatSplitLight
                variant="ski"
                a={skiT}
                b={liftT}
                labelLeft="Skiing (s)"
                labelRight="Lift (s)"
              />
            </div>
          )}

          {typeof leftN === 'number' && typeof rightN === 'number' && (
            <div className="stat-split-wrap-light">
              <div className="stat-split-title-light">Left vs Right turns</div>
              <StatSplitLight variant="lr" a={leftN} b={rightN} labelLeft="Left" labelRight="Right" />
            </div>
          )}
        </div>
      </div>

      <div className="card card-hover" style={{ marginBottom: 24 }}>
        <h2 className="card-title-results">Turn Analysis</h2>
        {showTurnArcViz && runsForViz ? (
          <TurnArcViz key={id} runs={runsForViz} width={600} height={400} />
        ) : (
          <TurnSignatureImage sessionId={id} />
        )}
        <p
          style={{
            marginTop: 12,
            fontSize: 12,
            color: 'var(--color-text-muted)',
            lineHeight: 1.45,
          }}
        >
          Blue = left turns · Green = right turns · Opacity reflects confidence
        </p>
      </div>

      <div className="card card-hover">
        <h2 className="card-title-results">Coach Notes</h2>
        {cleanedInsights.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 15, textAlign: 'center' }}>
            Ski more runs to unlock personalized coaching notes.
          </p>
        ) : (
          <>
            {coachingParts.subtitle ? (
              <p className="coach-notes-subtitle">{coachingParts.subtitle}</p>
            ) : null}
            <div className="coach-notes-cards">
              {Array.from(
                { length: Math.min(coachCardDefs.length, coachingBodies.length) },
                (_, i) => {
                  const def = coachCardDefs[i]
                  const body = coachingBodies[i]
                  const tier = coachScoreTier(def.tierScore)
                  const pill = formatCoachScorePill01(def.tierScore)
                  return (
                    <div
                      key={`coach-${i}-${def.label}`}
                      className={coachCardClass(tier)}
                      role="article"
                      aria-label={`${def.label} coaching note`}
                    >
                      <div className="coach-card-head">
                        <div className="coach-card-cat">
                          <span className="coach-card-icon" aria-hidden>
                            {def.icon}
                          </span>
                          <span className="coach-card-title">{def.label}</span>
                        </div>
                        <span className={coachScorePillClass(tier)}>{pill}</span>
                      </div>
                      <p className="coach-card-body">{body}</p>
                    </div>
                  )
                },
              )}
            </div>
            {coachingBodies.length > coachCardDefs.length ? (
              <div className="coach-notes-overflow">
                {coachingBodies.slice(coachCardDefs.length).map((line, j) => (
                  <p key={`coach-extra-${j}-${line.slice(0, 20)}`} className="coach-card-body coach-card-body--plain">
                    {line}
                  </p>
                ))}
              </div>
            ) : null}
          </>
        )}
        {warnings.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {warnings.map((w, i) => (
              <div key={`w-${i}`} className="warning-note-light">
                {w}
              </div>
            ))}
          </div>
        )}
      </div>

      <section className="next-run-card" aria-labelledby="next-run-heading">
        <h2 id="next-run-heading" className="next-run-card-label">
          Your focus for next time
        </h2>
        <p className="next-run-card-insight">{topInsight ?? NEXT_RUN_FALLBACK_INSIGHT}</p>
        {topInsight ? (
          <>
            {/* Eventually deep-link to the iOS app instead of web */}
            <a
              href={RECORD_NEXT_RUN_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="next-run-card-cta"
            >
              → Record your next run
            </a>
          </>
        ) : null}
      </section>

      {footerText ? <footer className="results-footer-meta">{footerText}</footer> : null}
    </div>
  )
}
