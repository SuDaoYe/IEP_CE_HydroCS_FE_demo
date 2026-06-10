import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { Field } from '../../types'

export default function FieldManagePage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [fields, setFields] = useState<Field[]>([])

  useEffect(() => {
    fetch('/api/admin/fields').then(r => r.json()).then(setFields)
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
        { key: 'fields', label: '田块管理', icon: '🌾', active: true },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="fields"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '田块总数', value: `${fields.length}` },
        { label: '已绑定', value: `${fields.filter(f => f.ownerId).length}` },
        { label: '未绑定', value: `${fields.filter(f => !f.ownerId).length}` },
      ]}
      tools={[]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">田块管理</h2>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">编号</th>
              <th className="text-left py-2 px-3">面积(亩)</th>
              <th className="text-left py-2 px-3">绑定用户</th>
              <th className="text-left py-2 px-3">作物</th>
              <th className="text-left py-2 px-3">生长周期</th>
            </tr>
          </thead>
          <tbody>
            {fields.map(f => (
              <tr key={f.id} className="border-b border-[#131820]">
                <td className="py-2 px-3 text-[#c8ccd0]">{f.name}</td>
                <td className="py-2 px-3">{f.area}</td>
                <td className="py-2 px-3">{f.ownerId ? (f.ownerId === 'u2' ? '张农户' : '李农户') : <span className="text-[#34d399]">空闲</span>}</td>
                <td className="py-2 px-3">{f.crop || '—'}</td>
                <td className="py-2 px-3">{f.growthStage || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
