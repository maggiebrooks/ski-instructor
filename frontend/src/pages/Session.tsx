import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { AxiosError } from 'axios'
import { deleteSession, getSession } from '../api'
import DemoModeBanner from '../components/DemoModeBanner'

const SESSION_POLL_MAX_FAILURES_DEFAULT = 8
const SESSION_POLL_MAX_FAILURES_404 = 2
const SESSION_POLL_INTERVAL_MS = 2000

const PROCESSING_STEP_LABELS = [
  'Validating upload',
  'Parsing sensors',
  'Detecting turns',
  'Scoring technique',
  'Generating insights',
  'Building report',
] as const

const METRIC_COACHING: Record<string, string> = {
  turn_rhythm:
    'Next run: focus on smoother, more consistent timing between turns. Count a steady rhythm as you ski.',
  pressure_management:
    'Next run: apply pressure earlier in the turn; exaggerate it at initiation.',
  edge_consistency:
    'Next run: commit to stronger edge angles through the middle of each turn.',
  rotary_stability:
    'Next run: reduce upper body rotation and let your skis guide the turn.',
  turn_symmetry:
    'Next run: match your left and right turns with equal weight and shape.',
  turn_shape_consistency:
    'Next run: aim for more consistent turn shapes instead of mixing sharp and wide turns.',
  turn_efficiency:
    'Next run: stay balanced and flowing; avoid unnecessary skidding or braking.',
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

const METRIC_INSIGHT_HINTS: Record<(typeof SCORE_KEYS)[number], readonly string[]> = {
  rotary_stability: ['rotary', 'rotation', 'upper body', 'steering'],
  edge_consistency: ['edge', 'angles'],
  pressure_management: ['pressure', 'initiation', 'weight'],
  turn_symmetry: ['symmetry', 'left and right', 'balanced'],
  turn_shape_consistency: ['shape', 'consistent turn', 'sharp and wide'],
  turn_rhythm: ['rhythm', 'timing', 'consistent timing'],
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

function processingUiStep(progress: string): number {
  const s = progress.toLowerCase()
  if (s === 'generating_plots') return 5
  if (s === 'generating_report' || s === 'analyzing') return 4
  if (s === 'running_pipeline') return 2
  if (s === 'parsing_sensor_data' || s === 'processing') return 1
  if (s === 'queued') return 0
  return 0
}

function isProcessingStepDone(stepIndex: number, current: number): boolean {
  if (current >= 4 && stepIndex === 3) return true
  return stepIndex < current
}

function isProcessingStepCurrent(stepIndex: number, current: number): boolean {
  return stepIndex === current
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

function formatDuration(s: number): string {
  const mins = Math.floor(s / 60)
  const secs = Math.round(s % 60)
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
  const vals = SCORE_KEYS.map((k) => scores[k]).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  return (vals.reduce((a, b) => a + b, 0) / vals.length) * 100
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

// TODO: replace with interactive SVG turn arcs (next prompt)
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
  const cur = processingUiStep(progress)
  const stageText = stageOverride ?? humanReadableStage(progress)

  return (
    <div className="processing-light-wrap">
      <div className="processing-light-card">
        <div className="processing-light-bar-track">
          <div className="processing-light-bar-fill" />
        </div>
        <div className="processing-light-top">
          <span className="upload-wordmark">Ski Recorder</span>
        </div>
        <div className="processing-light-id">{sessionId}</div>
        <p className="processing-light-stage">{stageText}</p>
        <div className="processing-stepper" role="list">
          {PROCESSING_STEP_LABELS.map((label, i) => {
            const done = isProcessingStepDone(i, cur)
            const current = isProcessingStepCurrent(i, cur)
            return (
              <div
                key={label}
                className={'processing-step-row' + (done ? ' processing-step-row--done' : '')}
                role="listitem"
              >
                {done ? (
                  <div className="processing-step-circle processing-step-circle--done" aria-hidden>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2 6l2.5 3L10 3"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                ) : current ? (
                  <div className="processing-step-circle processing-step-circle--current" aria-hidden>
                    <span className="processing-step-dot" />
                  </div>
                ) : (
                  <div className="processing-step-circle processing-step-circle--future" aria-hidden />
                )}
                <span className="processing-step-label">{label}</span>
              </div>
            )
          })}
        </div>
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
      navigate('/sessions')
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
          <p>Sessions are not persisted in demo mode. Upload a new session to analyze.</p>
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
          <p>Sessions are not persisted in demo mode. Upload a new session to analyze.</p>
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
        <Link to="/sessions" style={{ fontWeight: 600 }}>
          All sessions
        </Link>
        {' · '}
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
          <Link to="/sessions" style={{ fontWeight: 600 }}>
            All sessions
          </Link>
          {' · '}
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

  return (
    <div className="shell-results">
      <DemoModeBanner />

      <nav className="results-nav">
        <div className="results-nav-left">
          <Link to="/" style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Ski Recorder
          </Link>
          <span style={{ color: 'var(--color-text-muted)' }}> / </span>
          <Link to="/sessions" style={{ color: 'var(--color-text-secondary)' }}>
            Sessions
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
            const val = raw != null ? raw * 100 : null
            const pct = raw != null ? Math.max(0, Math.min(100, val ?? 0)) : 0
            const showTip =
              raw != null && raw < 0.6
                ? insightForMetric(key, cleanedInsights) ?? METRIC_COACHING[key] ?? null
                : null
            const dim = raw == null
            return (
              <div
                key={key}
                className={'score-row-light' + (dim ? ' score-row-light--dim' : '')}
              >
                <div className="score-row-light-head">
                  <span className="score-row-light-name">{SCORE_LABELS[key]}</span>
                  <span className="score-row-light-val">
                    {raw != null && val != null ? `${val.toFixed(0)}/100` : '-'}
                  </span>
                </div>
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
        <TurnSignatureImage sessionId={id} />
        <p
          style={{
            marginTop: 12,
            fontSize: 12,
            color: 'var(--color-text-muted)',
            lineHeight: 1.45,
          }}
        >
          Red = right turns · Blue = left turns · Dot size reflects turn radius
        </p>
      </div>

      <div className="card card-hover">
        <h2 className="card-title-results">Coach Notes</h2>
        {cleanedInsights.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 15, textAlign: 'center' }}>
            Ski more runs to unlock personalized coaching notes.
          </p>
        ) : (
          cleanedInsights.map((line, i) => (
            <div key={`${i}-${line.slice(0, 24)}`} className="coach-note-light">
              {line}
            </div>
          ))
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

      {footerText ? <footer className="results-footer-meta">{footerText}</footer> : null}

      <button
        type="button"
        className="delete-link-light"
        onClick={() => void handleDeleteSession()}
      >
        Delete this session
      </button>
    </div>
  )
}
