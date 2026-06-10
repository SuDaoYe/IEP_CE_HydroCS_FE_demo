import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { Field } from '../../types'

export default function MyFieldsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [fields, setFields] = useState<Field[]>([])
  const [irrigationData, setIrrigationData] = useState<Record<string, { predicted: number; date: string }[]>>({})

  useEffect(() => {
    fetch('/api/my/fields', { headers: { Authorization: 'Bearer mock' } })
      .then(r => r.json())
      .then(data => {
        setFields(data)
        data.forEach((f: Field) => {
          fetch(`/api/my/fields/${f.id}/irrigation`)
            .then(r => r.json())
            .then(records => {
              setIrrigationData(prev => ({ ...prev, [f.id]: records }))
            })
        })
      })
  }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <Layout
      title="HYDRO·CS 灌溉服务"
      username={user?.name ?? ''}
      onLogout={handleLogout}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'fields', label: '我的田块', icon: '🌾', active: true },
        { key: 'records', label: '灌溉记录', icon: '📋' },
      ]}
      activeMenu="fields"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/dashboard')
        else navigate('/dashboard/fields')
      }}
      panelItems={[
        { label: '已绑定田块', value: `${fields.length}` },
        { label: '总面积', value: `${fields.reduce((s, f) => s + f.area, 0).toFixed(1)} 亩` },
      ]}
      tools={[
        { label: '返回地图', onClick: () => navigate('/dashboard'), primary: true },
      ]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">我的田块</h2>
        {fields.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">暂无绑定田块，请在地图上框选并绑定。</p>
        ) : (
          <div className="flex flex-col gap-3">
            {fields.map(f => (
              <div key={f.id} className="bg-[var(--bg-panel)] border border-[var(--border)] rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-sm text-[var(--text-primary)] font-medium">{f.name}</h3>
                    <p className="text-xs text-[var(--text-muted)]">{f.area} 亩 · {f.crop} · {f.growthStage}</p>
                    <p className="text-[10px] text-[var(--text-muted)]">播种: {f.plantDate}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] text-[var(--text-muted)]">本周预测灌溉</div>
                    <div className="text-lg font-semibold text-[var(--accent)]">
                      {irrigationData[f.id]?.[0]?.predicted ?? '—'} m³
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => {
                      const centerLat = f.bounds.reduce((s: number, b: [number, number]) => s + b[0], 0) / f.bounds.length
                      const centerLng = f.bounds.reduce((s: number, b: [number, number]) => s + b[1], 0) / f.bounds.length
                      navigate('/dashboard', { state: { focusField: { lat: centerLat, lng: centerLng, zoom: 15 } } })
                    }}
                    className="px-3 py-1 text-[10px] bg-[var(--accent)] text-white rounded hover:opacity-80"
                  >
                    在地图上显示
                  </button>
                </div>
                {irrigationData[f.id] && irrigationData[f.id].length > 0 && (
                  <table className="w-full mt-3 text-[10px] text-[var(--text-body)] border-t border-[var(--border)] pt-2">
                    <thead>
                      <tr className="text-[var(--text-muted)]">
                        <th className="text-left py-1">日期</th>
                        <th className="text-left py-1">生长阶段</th>
                        <th className="text-right py-1">预测灌溉量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {irrigationData[f.id].map((r, i) => (
                        <tr key={i}>
                          <td className="py-1">{r.date}</td>
                          <td className="py-1">{f.growthStage}</td>
                          <td className="py-1 text-right text-[var(--accent)]">{r.predicted} m³</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
