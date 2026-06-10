import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'

interface Stats {
  activeUsers: number
  boundFields: number
  totalFields: number
  totalPredictedWater: number
  coverageRate: number
}

export default function DataOverviewPage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    fetch('/api/admin/stats').then(r => r.json()).then(setStats)
  }, [])

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
        { key: 'data', label: '数据总表', icon: '📊', active: true },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="data"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '区域总需水量', value: stats ? `${stats.totalPredictedWater} m³` : '—', highlight: true },
        { label: '活跃用户', value: `${stats?.activeUsers ?? '—'}` },
        { label: '已绑定田块', value: `${stats?.boundFields ?? '—'} / ${stats?.totalFields ?? '—'}` },
        { label: '灌溉覆盖率', value: `${stats?.coverageRate ?? '—'}%` },
      ]}
      tools={[{ label: '导出报表' }]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">数据总表</h2>
        <p className="text-xs text-[#6b7280] mb-4">
          区域总需水量: <span className="text-[#818cf8] font-semibold">{stats?.totalPredictedWater ?? '—'} m³</span> ·
          灌溉覆盖率: <span className="text-[#c8ccd0] font-semibold">{stats?.coverageRate ?? '—'}%</span>
        </p>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">用户</th>
              <th className="text-left py-2 px-3">田块</th>
              <th className="text-left py-2 px-3">作物</th>
              <th className="text-left py-2 px-3">周期</th>
              <th className="text-right py-2 px-3">预测灌溉量</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">张农户</td><td className="py-2 px-3">田块 A-01</td>
              <td className="py-2 px-3">小麦</td><td className="py-2 px-3">拔节期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">320 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">张农户</td><td className="py-2 px-3">田块 A-02</td>
              <td className="py-2 px-3">玉米</td><td className="py-2 px-3">抽穗期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">450 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">李农户</td><td className="py-2 px-3">田块 B-01</td>
              <td className="py-2 px-3">水稻</td><td className="py-2 px-3">分蘖期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">280 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">李农户</td><td className="py-2 px-3">田块 B-02</td>
              <td className="py-2 px-3">小麦</td><td className="py-2 px-3">灌浆期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">400 m³</td>
            </tr>
            <tr className="border-b border-[#1e2430]">
              <td className="py-2 px-3 text-[#c8ccd0] font-semibold" colSpan={4}>区域总需水量</td>
              <td className="py-2 px-3 text-right text-[#34d399] font-semibold">{stats?.totalPredictedWater ?? '—'} m³</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
