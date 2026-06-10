import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/AuthContext'
import { MapProvider } from './store/MapContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import MapView from './components/MapView'
import Login from './pages/Login'
import UserDashboardPage from './pages/user/UserDashboard'
import MyFieldsPage from './pages/user/MyFields'

function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 管理平台"
        username={user?.name ?? ''}
        isAdmin
        onLogout={() => { logout(); navigate('/login') }}
        menuItems={[
          { key: 'map', label: '地图总览', icon: '🗺️', active: true },
          { key: 'users', label: '用户管理', icon: '👥' },
          { key: 'fields', label: '田块管理', icon: '🌾' },
          { key: 'data', label: '数据总表', icon: '📊' },
          { key: 'settings', label: '参数微调', icon: '⚙️' },
        ]}
        activeMenu="map"
        onMenuClick={(key) => {
          if (key === 'map') navigate('/admin')
          else if (key === 'users') navigate('/admin/users')
          else if (key === 'fields') navigate('/admin/fields')
          else if (key === 'data') navigate('/admin/data')
          else if (key === 'settings') navigate('/admin/settings')
        }}
        panelItems={[
          { label: '区域总需水量（今日）', value: '1,280 m³', highlight: true },
          { label: '活跃用户', value: '2' },
          { label: '已绑定田块', value: '6' },
          { label: '灌溉覆盖率', value: '78%' },
        ]}
        tools={[
          { label: '上传气象数据' },
          { label: '参数微调' },
          { label: '导出报表' },
        ]}
      >
        <MapView />
      </Layout>
    </MapProvider>
  )
}

function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center h-full text-sm text-[#6b7280]">
      {title} — 待实现
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute requireAdmin><Placeholder title="用户管理" /></ProtectedRoute>} />
        <Route path="/admin/fields" element={<ProtectedRoute requireAdmin><Placeholder title="田块管理" /></ProtectedRoute>} />
        <Route path="/admin/data" element={<ProtectedRoute requireAdmin><Placeholder title="数据总表" /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute requireAdmin><Placeholder title="参数微调" /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><UserDashboardPage /></ProtectedRoute>} />
        <Route path="/dashboard/fields" element={<ProtectedRoute><MyFieldsPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
