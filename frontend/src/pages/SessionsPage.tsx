// NOTE: Hidden in demo mode. Re-enable route in App.tsx when persistence is ready (PostgreSQL migration, auth).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listSessions, type SessionListItem } from '../api'

const SCORE_KEYS = [
  'rotary_stability',
  'edge_consistency',
  'pressure_management',
  'turn_symmetry',
  'turn_shape_consistency',
  'turn_rhythm',
  'turn_efficiency',
] as const

function averageMovementScore(
  scores: Record<string, number | null> | undefined,
): number | null {
  if (!scores) return null
  const vals = SCORE_KEYS.map((k) => scores[k]).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

function scoreBadgeClass(avg: number | null): string {
  if (avg == null) return 'session-badge-light session-badge-light--na'
  const pct = avg * 100
  if (pct >= 70) return 'session-badge-light session-badge-light--high'
  if (pct >= 50) return 'session-badge-light session-badge-light--mid'
  return 'session-badge-light session-badge-light--low'
}

function sortSessionsNewestFirst(items: SessionListItem[]): SessionListItem[] {
  return [...items].sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0
    if (tb !== ta) return tb - ta
    return b.session_id.localeCompare(a.session_id)
  })
}

function formatSessionCardDate(session: SessionListItem): string {
  if (session.created_at) {
    const d = new Date(session.created_at)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    }
  }
  const sid = session.session_id
  if (/^\d{10,13}$/.test(sid)) {
    const d = new Date(Number(sid))
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    }
  }
  return sid.length > 14 ? `${sid.slice(0, 10)}…` : sid
}

function truncateInsight(text: string, max = 140): string {
  const t = text.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listSessions()
      .then((data) => {
        if (!cancelled) {
          const list = Array.isArray(data) ? data : []
          setSessions(sortSessionsNewestFirst(list))
        }
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load sessions')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  if (loading) {
    return (
      <div className="shell-sessions">
        <div className="plot-skeleton-light" style={{ maxWidth: 400, height: 100 }} />
        <p style={{ color: 'var(--color-text-muted)', marginTop: 16 }}>Loading sessions…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="shell-sessions">
        <p style={{ color: 'var(--color-danger)', marginBottom: 16 }}>{error}</p>
        <Link to="/" className="btn btn-primary">
          Back to upload
        </Link>
      </div>
    )
  }

  return (
    <div className="shell-sessions">
      <div className="sessions-page-head">
        <h1 className="sessions-page-title">My Sessions</h1>
        <Link to="/" className="btn btn-primary">
          New Upload
        </Link>
      </div>

      {sessions.length === 0 ? (
        <div className="sessions-empty-light">
          <p>No sessions yet.</p>
          <Link to="/">Upload your first run</Link>
        </div>
      ) : (
        <div className="sessions-grid-light">
          {sessions.map((session) => {
            const sid = session.session_id
            const avg = averageMovementScore(session.scores)
            const turns = session.summary?.turns
            const badgeLabel = avg != null ? `${(avg * 100).toFixed(0)}` : '-'

            return (
              <div key={sid} className="card card-hover session-card-light">
                <Link
                  to={`/session/${encodeURIComponent(sid)}`}
                  className="session-card-light-body"
                  style={{ display: 'block' }}
                >
                  <div className="session-card-light-date">{formatSessionCardDate(session)}</div>
                  <div className="session-card-light-meta">
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                      {turns != null ? `${turns} turns` : '- turns'}
                    </span>
                    <span className={scoreBadgeClass(avg)}>{badgeLabel}</span>
                  </div>
                  {session.top_insight ? (
                    <p className="session-card-light-insight">{truncateInsight(session.top_insight)}</p>
                  ) : (
                    <p className="session-card-light-insight" style={{ color: 'var(--color-text-muted)' }}>
                      Open for full coaching notes
                    </p>
                  )}
                  <div className="session-card-light-footer">
                    <span className="session-card-light-view">View</span>
                  </div>
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
