import axios from 'axios'

/**
 * Base URL for `/api/*` requests.
 * - Dev: unset → `/api` (Vite proxy to local backend). Override in `.env.local` if needed.
 * - Vercel/production: set `VITE_API_BASE_URL` to your Railway API origin + `/api` (build-time).
 */
const baseURL =
  (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '').trim() || '/api'

/** Generous read timeout for session list/detail (large reports, slow networks). */
const SESSION_READ_TIMEOUT_MS = 180_000

export const api = axios.create({
  baseURL,
})

/** Large uploads must hit the real API host; relative `/api` on Vercel is not Railway. */
function assertAbsoluteApiBaseForUpload() {
  if (typeof window === 'undefined' || !import.meta.env.PROD) return
  if (baseURL.startsWith('/')) {
    throw new Error(
      'Missing API URL for production: in Vercel set VITE_API_BASE_URL to your Railway API origin plus /api (e.g. https://<service>.up.railway.app/api), then redeploy.',
    )
  }
}

export async function uploadSession(file: File) {
  assertAbsoluteApiBaseForUpload()
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/upload-session', form, {
    timeout: 45 * 60 * 1000, // large ZIP + slow uplink (ms)
  })
  return res.data
}

export async function getSession(id: string) {
  const res = await api.get(`/session/${id}`, {
    timeout: SESSION_READ_TIMEOUT_MS,
  })
  return res.data
}

export interface SessionListItem {
  session_id: string
  status?: string
  summary?: {
    runs?: number | null
    turns?: number | null
    vertical_m?: number | null
    max_speed_kmh?: number | null
    duration_s?: number | null
  }
  scores?: Record<string, number | null>
  top_insight?: string | null
  /** ISO 8601 from server (report file mtime); used for sorting. */
  created_at?: string
}

export async function listSessions(): Promise<SessionListItem[]> {
  const res = await api.get<SessionListItem[]>('/sessions', {
    timeout: SESSION_READ_TIMEOUT_MS,
  })
  return res.data
}

export async function deleteSession(id: string) {
  const res = await api.delete(`/session/${id}`, {
    timeout: 60_000,
  })
  return res.data
}
