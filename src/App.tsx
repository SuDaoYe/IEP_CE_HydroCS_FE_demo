import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './store/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import AdminDashboardPage from './pages/admin/AdminDashboard'
import UserManagePage from './pages/admin/UserManage'
import FieldManagePage from './pages/admin/FieldManage'
import DataOverviewPage from './pages/admin/DataOverview'
import SettingsPage from './pages/admin/Settings'
import UserDashboardPage from './pages/user/UserDashboard'
import MyFieldsPage from './pages/user/MyFields'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboardPage /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute requireAdmin><UserManagePage /></ProtectedRoute>} />
        <Route path="/admin/fields" element={<ProtectedRoute requireAdmin><FieldManagePage /></ProtectedRoute>} />
        <Route path="/admin/data" element={<ProtectedRoute requireAdmin><DataOverviewPage /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute requireAdmin><SettingsPage /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><UserDashboardPage /></ProtectedRoute>} />
        <Route path="/dashboard/fields" element={<ProtectedRoute><MyFieldsPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
