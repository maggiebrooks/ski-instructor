import { useEffect, useState, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { deleteSession, getSession } from '../api'
import Progress from '../components/Progress'

interface Summary {
  runs: number | null
  turns: number | null
  vertical_m: number | null
  max_speed_kmh: number | null
  duration_s: number | null
}

interface Report {
  summary?: Summary
  scores?: Record<string, number | null>
  insights?: string[]
  warnings?: string[]
  score_confidence?: 'low' | 'medium' | 'high'
  top_insight?: string | null
}

interface SessionData {
  session_id: string
  status: string
  progress: string
  report: Report | null
}

export default function Session() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<SessionData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const intervalRef = useRef<number | null>(null)
  const copyTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    if (!id) return

    async function poll() {
      try {
        const res = await getSession(id!)
        setData(res)
        if (res.status === 'complete' || res.status === 'error') {
          if (intervalRef.current) clearInterval(intervalRef.current)
        }
      } catch {
        setError('Failed to load session')
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }

    poll()
    intervalRef.current = window.setInterval(poll, 3000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [id])

  useEffect(() => {
    setCopied(false)
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

  if (error) {
    return (
      <div style={{ padding: 40 }}>
        <p style={{ color: 'crimson' }}>{error}</p>
        <Link to="/sessions">All sessions</Link>
        {' · '}
        <Link to="/">Back to upload</Link>
      </div>
    )
  }

  if (!data) {
    return <div style={{ padding: 40 }}>Loading...</div>
  }

  if (data.status === 'error') {
    const errMsg = (data as { error?: string }).error
    return (
      <div style={{ padding: 40 }}>
        <h2>Processing Failed</h2>
        <p style={{ color: 'crimson' }}>
          The pipeline encountered an error. Try uploading again.
        </p>
        {errMsg && (
          <pre style={{
            marginTop: 16,
            padding: 12,
            background: '#f5f5f5',
            fontSize: 12,
            overflow: 'auto',
            maxHeight: 200,
          }}>
            {errMsg}
          </pre>
        )}
        <Link to="/sessions">All sessions</Link>
        {' · '}
        <Link to="/">Back to upload</Link>
      </div>
    )
  }

  if (data.status !== 'complete') {
    return (
      <div style={{ padding: 40 }}>
        <div style={{ marginBottom: 16 }}>
          <Link to="/sessions">&larr; All sessions</Link>
          {' · '}
          <Link to="/">New upload</Link>
        </div>
        <h2>Processing Session</h2>
        <Progress stage={data.progress} />
      </div>
    )
  }

  const report: Report = data.report ?? {}
  const scores = report.scores ?? {}
  const insights = report.insights ?? []
  const cleanedInsights = insights.filter((i: string) => i.trim().length > 0)
  const topInsight = report.top_insight ?? null
  const warnings = report.warnings ?? []
  const scoreConfidence = report.score_confidence ?? 'unknown'

  const SCORE_KEYS = [
    'rotary_stability',
    'edge_consistency',
    'pressure_management',
    'turn_symmetry',
    'turn_shape_consistency',
    'turn_rhythm',
    'turn_efficiency',
  ]
  const validScores = SCORE_KEYS.map((k) => scores[k]).filter(
    (v): v is number => v != null,
  )
  /** Average of known movement score dimensions (null if none present). */
  const averageScore =
    validScores.length > 0
      ? validScores.reduce((a, b) => a + b, 0) / validScores.length
      : null

  const supportingInsights = topInsight
    ? cleanedInsights.filter((i) => i.trim() !== topInsight.trim())
    : cleanedInsights

  const summary = report.summary

  return (
    <div style={{ padding: 40, maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 16, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <Link to="/sessions">&larr; All sessions</Link>
        <Link to="/">New upload</Link>
      </div>

      <div
        style={{
          border: '1px solid #ddd',
          borderRadius: 10,
          padding: 16,
          marginBottom: 20,
          background: '#fafafa',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>
              Ski Session Result
            </div>
            <div style={{ fontSize: 12, color: '#aaa', marginBottom: 10 }}>
              AI analysis of this ski run
            </div>
            <div style={{ fontSize: 20, fontWeight: 'bold', marginBottom: 8 }}>
              {topInsight?.trim() ||
                'Next run: focus on smooth, controlled skiing.'}
            </div>
            {averageScore !== null && (
              <div style={{ fontSize: 14, color: '#555' }}>
                Overall Score: {(averageScore * 100).toFixed(0)}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={copyLink}
              style={{
                padding: '8px 12px',
                fontSize: 12,
                cursor: 'pointer',
                height: 'fit-content',
                flexShrink: 0,
                minHeight: 36,
                minWidth: 88,
                opacity: 0.9,
              }}
            >
              {copied ? 'Copied!' : 'Copy Link'}
            </button>
            <button
              type="button"
              onClick={() => void handleDeleteSession()}
              style={{
                padding: '8px 12px',
                fontSize: 12,
                cursor: 'pointer',
                height: 'fit-content',
                flexShrink: 0,
                minHeight: 36,
                border: '1px solid #c99',
                background: '#fff8f8',
                color: '#922',
              }}
            >
              Delete Session
            </button>
          </div>
        </div>
      </div>

      <hr style={{ margin: '20px 0', opacity: 0.2 }} />

      {validScores.length > 0 && (
        <>
          <h3>Movement Scores</h3>
          <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 24 }}>
            <tbody>
              {Object.entries(scores).map(([key, val]) =>
                val != null ? (
                  <tr key={key}>
                    <td style={labelStyle}>{formatScoreLabel(key)}</td>
                    <td style={valStyle}>{(val * 100).toFixed(0)}</td>
                  </tr>
                ) : null,
              )}
            </tbody>
          </table>
        </>
      )}

      <div className="insights-section">
        <h3>Supporting Insights</h3>
        {supportingInsights.length === 0 ? (
          <div style={{ color: '#666', fontSize: 14 }}>No additional insights</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {supportingInsights.map((insight: string, i: number) => (
              <li key={i} style={{ marginBottom: 6 }}>
                {insight}
              </li>
            ))}
          </ul>
        )}
      </div>

      {warnings.length > 0 && (
        <div className="warning-banner" style={{ marginTop: 20 }}>
          {warnings.map((w: string, i: number) => (
            <div key={i}>⚠️ {w}</div>
          ))}
        </div>
      )}

      {scoreConfidence !== 'unknown' && (
        <div
          className={`score-confidence ${scoreConfidence}`}
          style={{ marginTop: 16, fontSize: 14, color: '#555' }}
        >
          {scoreConfidence === 'high' && 'Confidence: High'}
          {scoreConfidence === 'medium' && 'Confidence: Medium'}
          {scoreConfidence === 'low' && 'Confidence: Low'}
        </div>
      )}

      {summary && (
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            marginTop: 24,
            marginBottom: 24,
          }}
        >
          <tbody>
            {summary.runs != null && (
              <tr>
                <td style={labelStyle}>Runs</td>
                <td style={valStyle}>{summary.runs}</td>
              </tr>
            )}
            {summary.turns != null && (
              <tr>
                <td style={labelStyle}>Turns</td>
                <td style={valStyle}>{summary.turns}</td>
              </tr>
            )}
            {summary.vertical_m != null && (
              <tr>
                <td style={labelStyle}>Vertical</td>
                <td style={valStyle}>{Math.round(summary.vertical_m)} m</td>
              </tr>
            )}
            {summary.max_speed_kmh != null && (
              <tr>
                <td style={labelStyle}>Max Speed</td>
                <td style={valStyle}>{summary.max_speed_kmh.toFixed(1)} km/h</td>
              </tr>
            )}
            {summary.duration_s != null && (
              <tr>
                <td style={labelStyle}>Duration</td>
                <td style={valStyle}>
                  {formatDuration(summary.duration_s as number)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <h3>Turn Signature</h3>
      <img
        src={`/api/session/${id}/plot/${id}_turn_signature.png`}
        alt="Turn signature plot"
        style={{ width: '100%', maxWidth: 640, border: '1px solid #ddd' }}
      />
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  padding: '6px 12px 6px 0',
  color: '#666',
  borderBottom: '1px solid #eee',
}

const valStyle: React.CSSProperties = {
  padding: '6px 0',
  fontWeight: 600,
  borderBottom: '1px solid #eee',
}

function formatDuration(s: number): string {
  const mins = Math.floor(s / 60)
  const secs = Math.round(s % 60)
  return `${mins}m ${secs}s`
}

function formatScoreLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
