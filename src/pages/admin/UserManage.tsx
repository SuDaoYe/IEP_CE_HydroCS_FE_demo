import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { User } from '../../types'

export default function UserManagePage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState<Omit<User, 'password'>[]>([])

  useEffect(() => {
    fetch('/api/admin/users')
      .then(r => r.json())
      .then(setUsers)
  }, [])

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥', active: true },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="users"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '用户总数', value: `${users.length}` },
        { label: '管理员', value: `${users.filter(u => u.role === 'admin').length}` },
        { label: '农户', value: `${users.filter(u => u.role === 'user').length}` },
      ]}
      tools={[]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">用户管理</h2>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">用户名</th>
              <th className="text-left py-2 px-3">姓名</th>
              <th className="text-left py-2 px-3">角色</th>
              <th className="text-left py-2 px-3">电话</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[#131820]">
                <td className="py-2 px-3 text-[#c8ccd0]">{u.username}</td>
                <td className="py-2 px-3">{u.name}</td>
                <td className="py-2 px-3">
                  <span className={u.role === 'admin' ? 'text-amber-400' : 'text-[#9ca3af]'}>
                    {u.role === 'admin' ? '管理员' : '农户'}
                  </span>
                </td>
                <td className="py-2 px-3">{u.phone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
