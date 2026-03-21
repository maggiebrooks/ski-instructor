import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteSession, listSessions, type SessionListItem } from '../api'

const SCORE_KEYS = [
  'rotary_stability',
  'edge_consistency',
  'pressure_management',
  'turn_symmetry',
  'turn_shape_consistency',
  'turn_rhythm',
  'turn_efficiency',
] as const

function averageMovementScore(scores: Record<string, number | null> | undefined): number | null {
  if (!scores) return null
  const vals = SCORE_KEYS.map((k) => scores[k]).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

/** Newest first; tie-break by session_id for stable order. */
function sortSessionsNewestFirst(items: SessionListItem[]): SessionListItem[] {
  return [...items].sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0
    if (tb !== ta) return tb - ta
    return b.session_id.localeCompare(a.session_id)
  })
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm('Delete this session?')) return
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
    } catch {
      setError('Failed to delete session')
    }
  }

  const copyLink = (id: string) => {
    const url = `${window.location.origin}/session/${encodeURIComponent(id)}`
    void navigator.clipboard.writeText(url)
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    setCopiedId(id)
    copyTimeoutRef.current = setTimeout(() => {
      setCopiedId(null)
      copyTimeoutRef.current = null
    }, 2000)
  }

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
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  if (loading) {
    return <div style={{ padding: 40 }}>Loading sessions...</div>
  }

  if (error) {
    return (
      <div style={{ padding: 40 }}>
        <p style={{ color: 'crimson' }}>{error}</p>
        <Link to="/">Back to upload</Link>
      </div>
    )
  }

  return (
    <div style={{ padding: 40, maxWidth: 640, margin: '0 auto' }}>
      <Link to="/" style={{ display: 'inline-block', marginBottom: 16 }}>
        &larr; Upload new session
      </Link>

      <h1>Your Sessions</h1>
      <p style={{ color: '#666', marginBottom: 24 }}>
        Completed analyses. Open a session to see full results or share the link.
      </p>

      {sessions.length === 0 && (
        <div style={{ color: '#666' }}>No sessions yet. Upload a zip from the home page.</div>
      )}

      {sessions.map((session, index) => {
        const id = session.session_id
        const isLatest = index === 0 && sessions.length > 0
        const avg = averageMovementScore(session.scores)
        const status = session.status ?? 'complete'
        const shortId = id.length > 12 ? `${id.slice(0, 8)}…` : id.slice(0, 8)
        const turns = session.summary?.turns
        const baseBg = isLatest ? '#fafafa' : '#fff'
        const hoverBg = isLatest ? '#f0f0f0' : '#f7f7f7'

        return (
          <div
            key={id}
            style={{
              marginBottom: 12,
              border: isLatest ? '2px solid #333' : '1px solid #ddd',
              borderRadius: 8,
              background: baseBg,
              overflow: 'hidden',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = hoverBg
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = baseBg
            }}
          >
            <Link
              to={`/session/${encodeURIComponent(id)}`}
              style={{
                display: 'block',
                padding: 14,
                paddingBottom: 8,
                textDecoration: 'none',
                color: 'inherit',
              }}
            >
              {isLatest && (
                <div style={{ fontSize: 12, color: '#888', marginBottom: 4, fontWeight: 600 }}>
                  Latest Run
                </div>
              )}
              <div style={{ fontWeight: 700 }}>Session {shortId}</div>
              <div style={{ fontSize: 14, color: '#555', marginTop: 4 }}>
                Status: {status}
                {turns != null && ` · ${turns} turns`}
              </div>
              {avg != null && (
                <div style={{ marginTop: 6, fontWeight: 600 }}>
                  Score: {(avg * 100).toFixed(0)}
                </div>
              )}
              {session.top_insight && (
                <div style={{ marginTop: 8, fontSize: 14, color: '#444', lineHeight: 1.4 }}>
                  {session.top_insight}
                </div>
              )}
            </Link>
            <div
              style={{
                padding: '0 14px 14px',
                display: 'flex',
                gap: 8,
                flexWrap: 'wrap',
              }}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  copyLink(id)
                }}
                style={{
                  marginTop: 0,
                  padding: '6px 10px',
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  border: '1px solid #ccc',
                  borderRadius: 6,
                  background: '#fff',
                }}
              >
                {copiedId === id ? 'Copied!' : 'Copy Link'}
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  void handleDelete(id)
                }}
                style={{
                  marginTop: 0,
                  padding: '6px 10px',
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  border: '1px solid #c99',
                  borderRadius: 6,
                  background: '#fff8f8',
                  color: '#922',
                }}
              >
                Delete
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
