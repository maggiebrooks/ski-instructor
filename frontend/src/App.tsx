import { BrowserRouter, Routes, Route, Link, Navigate } from 'react-router-dom'
import Upload from './pages/Upload'
import Session from './pages/Session'

function NotFoundPage() {
  return (
    <div className="not-found-page">
      <div className="not-found-inner">
        <span className="upload-wordmark">Ski Recorder</span>
        <h1 className="not-found-title">Page not found</h1>
        <p className="not-found-muted">
          {"The page you're looking for doesn't exist."}
        </p>
        <Link to="/" className="btn btn-primary">
          Go to Upload
        </Link>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Upload />} />
        <Route path="/sessions" element={<Navigate to="/" replace />} />
        <Route path="/session/:id" element={<Session />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
