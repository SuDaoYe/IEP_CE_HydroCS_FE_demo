import { useEffect } from 'react'
import { Navigate, Outlet, Route, Routes, BrowserRouter, useLocation } from 'react-router-dom'
import TopBar from './components/TopBar'
import { DesktopRail } from './components/ToolRail'
import ConnectionBanner from './components/ConnectionBanner'
import { Toast } from './components/ui'
import { useAuth } from './store/auth'
import Login from './pages/Login'
import Workspace from './pages/Workspace'
import MyFields from './pages/MyFields'
import History from './pages/History'
import Admin from './pages/Admin'

function AppShell() {
  const token = useAuth((state) => state.token)
  const ready = useAuth((state) => state.ready)
  const bootstrap = useAuth((state) => state.bootstrap)
  const location = useLocation()

  useEffect(() => {
    bootstrap()
  }, [bootstrap])

  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (!ready) return null

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <DesktopRail />
        <Outlet />
      </div>
      <Toast />
      <ConnectionBanner />
    </div>
  )
}

function AdminOnly() {
  const user = useAuth((state) => state.user)
  if (user && user.role !== 'admin') return <Navigate to="/" replace />
  return <Admin />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Workspace />} />
          <Route path="/fields" element={<MyFields />} />
          <Route path="/history" element={<History />} />
          <Route path="/admin" element={<AdminOnly />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
