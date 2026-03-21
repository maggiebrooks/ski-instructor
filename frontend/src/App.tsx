import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Upload from './pages/Upload'
import Session from './pages/Session'
import SessionsPage from './pages/SessionsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Upload />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/session/:id" element={<Session />} />
      </Routes>
    </BrowserRouter>
  )
}
