import { useCallback, useId, useRef, useState, type DragEvent } from 'react'
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
  const [isDragging, setIsDragging] = useState(false)
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

  const handleDragEnter = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragOver = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLLabelElement>) => {
    const next = e.relatedTarget as Node | null
    if (next && e.currentTarget.contains(next)) return
    setIsDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const list = e.dataTransfer.files
    pickFiles(list.length > 0 ? list : null)
  }

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
          Ski Recorder uses your iPhone&apos;s built-in motion sensors to record your ski sessions,
          then analyzes your technique across six coaching dimensions used by PSIA-certified
          instructors: edge control, rotary stability, pressure management, turn symmetry, turn
          shape, and rhythm.
        </p>
        <p className="upload-light-sub upload-light-sub-caveat">
          Upload a session ZIP recorded with the Ski Recorder iOS app to get started. Processing
          runs on a free-tier server and typically takes 30–90 seconds.
        </p>

        <label
          htmlFor={inputId}
          className={
            'upload-drop-card' + (isDragging ? ' upload-drop-card--dragging' : '')
          }
          style={{ cursor: 'pointer', display: 'block' }}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
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

        <div className="upload-footer-stack">
          <p className="upload-footer-line">
            Don&apos;t have the iOS app yet? Download a sample session below to try the analyzer.
          </p>
          {/* Sample ZIP must be placed at frontend/public/sample-session.zip —
              Vite serves public/ at root. File is gitignored if large;
              add to .gitignore if needed. */}
          <a
            href="/sample-session.zip"
            download="sample-session.zip"
            className="sample-download-link"
          >
            ↓ Download sample session
          </a>
        </div>
      </div>
    </div>
  )
}
