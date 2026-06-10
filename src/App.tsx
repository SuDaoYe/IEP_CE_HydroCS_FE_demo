import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './store/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><div>Admin Dashboard</div></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><div>User Dashboard</div></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
