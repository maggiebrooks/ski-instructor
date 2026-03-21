import axios from 'axios'

/** Dev: proxy `/api` via Vite. If proxy fails, set `VITE_API_BASE_URL=http://127.0.0.1:8000/api` in `.env.local`. */
const baseURL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || '/api'

export const api = axios.create({
  baseURL,
})

export async function uploadSession(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/upload-session', form)
  return res.data
}

export async function getSession(id: string) {
  const res = await api.get(`/session/${id}`)
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
  const res = await api.get<SessionListItem[]>('/sessions')
  return res.data
}

export async function deleteSession(id: string) {
  const res = await api.delete(`/session/${id}`)
  return res.data
}
