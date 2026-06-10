import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'

export default function SettingsPage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥' },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️', active: true },
      ]}
      activeMenu="settings"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else navigate('/admin/settings')
      }}
      panelItems={[
        { label: '气象数据', value: '正常', sub: '更新: 2026-06-10 08:00' },
        { label: '温度', value: '28.5°C' },
        { label: '湿度', value: '65%' },
        { label: '降雨量', value: '12.3 mm' },
      ]}
      tools={[
        { label: '上传气象数据' },
        { label: '参数微调' },
      ]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">参数微调</h2>
        <p className="text-xs text-[var(--text-muted)] mb-4">以下功能按钮预留，暂无实际功能。</p>
        <div className="flex flex-col gap-3 max-w-sm">
          <button className="w-full py-2 text-xs text-[var(--text-body)] bg-[var(--bg-panel)] border border-[var(--border)] rounded-md hover:text-[var(--text-primary)]">
            上传最新气象数据
          </button>
          <button className="w-full py-2 text-xs text-[var(--text-body)] bg-[var(--bg-panel)] border border-[var(--border)] rounded-md hover:text-[var(--text-primary)]">
            灌溉模型参数调整
          </button>
          <button className="w-full py-2 text-xs text-[var(--text-body)] bg-[var(--bg-panel)] border border-[var(--border)] rounded-md hover:text-[var(--text-primary)]">
            田块识别阈值设置
          </button>
          <button className="w-full py-2 text-xs text-[var(--text-body)] bg-[var(--bg-panel)] border border-[var(--border)] rounded-md hover:text-[var(--text-primary)]">
            系统通知配置
          </button>
        </div>
      </div>
    </Layout>
  )
}
