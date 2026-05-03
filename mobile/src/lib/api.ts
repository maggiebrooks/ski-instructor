import axios, { AxiosError } from 'axios';

import { API_BASE_URL } from '../config';
import type { SessionQualityFile } from './csv';

export type UploadResponse = {
  session_id: string;
  status?: string;
  duplicate?: boolean;
  detail?: string;
};

export type SessionReport = {
  summary?: {
    runs?: number | null;
    turns?: number | null;
    vertical_m?: number | null;
    max_speed_kmh?: number | null;
    duration_s?: number | null;
  };
  scores?: Record<string, number | null>;
  insights?: string[];
  warnings?: string[];
  score_confidence?: 'low' | 'medium' | 'high';
  filtered_turn_count?: number;
  total_turn_count?: number;
  top_insight?: string | null;
  /** When the API echoes mobile session_quality from ZIP (future); optional. */
  session_quality?: SessionQualityFile;
};

export type SessionStatusResponse = {
  session_id: string;
  status: string;
  progress: string;
  report: SessionReport | null;
  error?: string;
};

/**
 * POST a ZIP file at `uri` (a local `file://` URI or `expo-file-system` cache
 * path) to the backend's `/api/upload-session` endpoint as multipart/form-data
 * under the field name `file`.
 */
export async function uploadSessionZip(
  uri: string,
  filename = 'session.zip',
  onProgress?: (fraction: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  // React Native's FormData accepts this object shape for native file uploads;
  // the cast keeps TS happy since the DOM type expects a Blob.
  form.append('file', {
    uri,
    name: filename,
    type: 'application/zip',
  } as unknown as Blob);

  const url = `${API_BASE_URL.replace(/\/$/, '')}/api/upload-session`;

  const res = await axios.post<UploadResponse>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 45 * 60 * 1000,
    onUploadProgress: (e) => {
      if (!onProgress) return;
      const total = e.total ?? 0;
      if (total > 0) onProgress(Math.min(1, e.loaded / total));
    },
  });
  return res.data;
}

/** Fetch a session's current status/report (poll while processing). */
export async function getSession(sessionId: string): Promise<SessionStatusResponse> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/api/session/${encodeURIComponent(sessionId)}`;
  const res = await axios.get<SessionStatusResponse>(url, { timeout: 180_000 });
  return res.data;
}

export function describeUploadError(err: unknown): string {
  if (err instanceof AxiosError) {
    if (err.code === 'ECONNABORTED') return 'Upload timed out.';
    const data = err.response?.data;
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === 'string') return d;
    }
    if (!err.response) {
      return (
        `Network error reaching ${API_BASE_URL}. ` +
        `If you are on a physical device, set API_BASE_URL in src/config.ts ` +
        `to your dev Mac's LAN IP (e.g. http://192.168.1.42:8000).`
      );
    }
    return `Upload failed (HTTP ${err.response.status})`;
  }
  return err instanceof Error ? err.message : String(err);
}
