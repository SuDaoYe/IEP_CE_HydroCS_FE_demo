import { Routes, Route, Navigate } from 'react-router-dom'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<div>Login placeholder</div>} />
      <Route path="*" element={<div>404</div>} />
    </Routes>
  )
}
