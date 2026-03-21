import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { uploadSession } from '../api'
import { AxiosError } from 'axios'

export default function Upload() {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const navigate = useNavigate()

  async function handleUpload() {
    if (!file) return
    setError(null)
    setUploading(true)

    try {
      const res = await uploadSession(file)
      navigate(`/session/${res.session_id}`)
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      const msg = axErr.response?.data?.detail || 'Upload failed'
      setError(msg)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={{ padding: 40, maxWidth: 480, margin: '0 auto' }}>
      <p style={{ marginBottom: 16 }}>
        <Link to="/sessions">View past sessions</Link>
      </p>
      <h1>Ski Analyzer</h1>
      <p style={{ color: '#666' }}>
        Upload a Sensor Logger session (.zip) to analyze your skiing.
      </p>

      <input
        type="file"
        accept=".zip"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
        style={{ display: 'block', margin: '20px 0' }}
      />

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        style={{
          padding: '10px 24px',
          fontSize: 16,
          cursor: file && !uploading ? 'pointer' : 'not-allowed',
        }}
      >
        {uploading ? 'Uploading...' : 'Upload Session'}
      </button>

      {error && (
        <p style={{ color: 'crimson', marginTop: 16 }}>{error}</p>
      )}
    </div>
  )
}
