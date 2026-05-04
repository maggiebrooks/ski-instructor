import { useCallback, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'

import { uploadSession } from '../api'

function formatUploadError(err: unknown): string {
  if (err instanceof Error && !('isAxiosError' in err)) {
    return err.message
  }
  const ax = err as AxiosError<{ detail?: string | { msg?: string }[] }>
  if (ax.code === 'ECONNABORTED') {
    return 'Upload timed out. Try again, use a faster connection, or a smaller ZIP.'
  }
  if (!ax.response) {
    return (
      ax.message ||
      'Network error. Open DevTools → Network, confirm the upload goes to your Railway …/api host.'
    )
  }
  const d = ax.response.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((x) =>
        typeof x === 'object' && x && 'msg' in x
          ? String((x as { msg: string }).msg)
          : JSON.stringify(x),
      )
      .join('; ')
  }
  return `Upload failed (HTTP ${ax.response.status})`
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function UploadArrowIcon() {
  return (
    <svg
      className="upload-drop-icon"
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
    >
      <path
        d="M16 6v14M10 12l6-6 6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M8 26h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export default function Upload() {
  const inputId = useId()
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const pickFiles = useCallback((list: FileList | null) => {
    const f = list?.[0]
    if (f && f.name.toLowerCase().endsWith('.zip')) {
      setFile(f)
      setError(null)
    } else if (f) {
      setError('Please choose a .zip file.')
      setFile(null)
    }
  }, [])

  async function handleUpload() {
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const res = await uploadSession(file)
      navigate(`/session/${res.session_id}`, { state: { fromUpload: true } })
    } catch (err) {
      setError(formatUploadError(err))
    } finally {
      setUploading(false)
    }
  }

  const triggerBrowse = () => inputRef.current?.click()

  return (
    <div className="upload-light-page">
      <div className="upload-light-inner">
        <div className="upload-light-top">
          <span className="upload-wordmark">Ski Recorder</span>
          <Link to="/sessions" className="upload-light-sessions">
            My Sessions
          </Link>
        </div>

        <h1 className="upload-light-headline">Analyze Your Run</h1>
        <p className="upload-light-sub">
          Upload a session recorded with Ski Recorder on iPhone. AI-powered technique
          feedback in under 60 seconds.
        </p>

        <label htmlFor={inputId} className="upload-drop-card" style={{ cursor: 'pointer', display: 'block' }}>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept=".zip"
            className="visually-hidden"
            onChange={(e) => pickFiles(e.target.files)}
          />
          {!file ? (
            <>
              <UploadArrowIcon />
              <p className="upload-drop-line1">Drop your .zip file here</p>
              <button
                type="button"
                className="upload-drop-browse"
                onClick={(e) => {
                  e.preventDefault()
                  triggerBrowse()
                }}
              >
                or click to browse
              </button>
            </>
          ) : (
            <div className="upload-file-picked">
              <span className="upload-check" aria-hidden>
                <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                  <path
                    d="M4.5 11l4 5L17.5 6"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <span className="upload-file-picked-name">{file.name}</span>
              <span className="upload-file-picked-size">{formatBytes(file.size)}</span>
            </div>
          )}
        </label>

        <div className="upload-cta-row">
          {uploading ? (
            <button type="button" className="btn btn-primary upload-cta-full" disabled>
              <span className="spinner" aria-hidden />
              Uploading…
            </button>
          ) : file ? (
            <button
              type="button"
              className="btn btn-primary upload-cta-full"
              onClick={() => void handleUpload()}
            >
              Analyze Session
            </button>
          ) : (
            <button type="button" className="btn btn-upload-muted upload-cta-full" disabled>
              Analyze Session
            </button>
          )}
          <p className="upload-helper">
            {!file && !uploading ? 'Select a .zip file above to continue' : '\u00a0'}
          </p>
        </div>

        {error && <p className="upload-error-text">{error}</p>}

        <p className="upload-footer-line">Recorded with Ski Recorder for iPhone</p>
      </div>
    </div>
  )
}
