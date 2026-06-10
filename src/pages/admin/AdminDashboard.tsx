import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import { MapProvider } from '../../store/MapContext'
import Layout from '../../components/Layout'
import MapView from '../../components/MapView'

export default function AdminDashboardPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 管理平台"
        username={user?.name ?? ''}
        isAdmin
        onLogout={handleLogout}
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
