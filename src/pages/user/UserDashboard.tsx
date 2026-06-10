import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import { MapProvider } from '../../store/MapContext'
import Layout from '../../components/Layout'
import MapView from '../../components/MapView'
import type { Field } from '../../types'

export default function UserDashboardPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [nearbyFields, setNearbyFields] = useState<Field[]>([])
  const [selectedField, setSelectedField] = useState<Field | null>(null)
  const [myFields, setMyFields] = useState<Field[]>([])
  const [showBindDialog, setShowBindDialog] = useState(false)
  const [crop, setCrop] = useState('')
  const [growthStage, setGrowthStage] = useState('')
  const [plantDate, setPlantDate] = useState('')
  const [irrigation, setIrrigation] = useState<{ predicted: number; date: string }[]>([])

  useEffect(() => {
    fetch('/api/fields/nearby?lat=30.26&lng=120.17')
      .then(r => r.json())
      .then(setNearbyFields)
  }, [])

  useEffect(() => {
    fetch('/api/my/fields', { headers: { Authorization: `Bearer mock` } })
      .then(r => r.json())
      .then(setMyFields)
  }, [])

  const handleFieldSelect = useCallback(async (field: Field) => {
    setSelectedField(field)
    const res = await fetch(`/api/my/fields/${field.id}/irrigation`)
    const data = await res.json()
    setIrrigation(data)
  }, [])

  const handleBind = useCallback(async () => {
    if (!selectedField || !crop || !growthStage) return
    await fetch('/api/my/fields/bind', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer mock' },
      body: JSON.stringify({
        fieldId: selectedField.id,
        ownerId: user!.id,
        crop,
        growthStage,
        plantDate: plantDate || new Date().toISOString().split('T')[0],
      }),
    })
    setShowBindDialog(false)
    const res = await fetch('/api/my/fields', { headers: { Authorization: `Bearer mock` } })
    setMyFields(await res.json())
  }, [selectedField, crop, growthStage, plantDate, user])

  const handleLogout = () => { logout(); navigate('/login') }

  const panelItems = [
    { label: '当前位置', value: '余杭区' },
    ...(selectedField
      ? [
          { label: '选中田块', value: selectedField.name, sub: `${selectedField.area} 亩${selectedField.crop ? ' · ' + selectedField.crop : ''}` },
          ...(irrigation.length > 0
            ? [{ label: '本周预测灌溉量', value: `${irrigation[0].predicted} m³`, highlight: true as const }]
            : []),
          ...(selectedField.crop
            ? [{ label: '作物信息', value: `${selectedField.crop} · ${selectedField.growthStage}`, sub: `播种: ${selectedField.plantDate}` }]
            : []),
        ]
      : [{ label: '选中田块', value: '—', sub: '点击地图上的田块' }]),
  ]

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 灌溉服务"
        username={user?.name ?? ''}
        onLogout={handleLogout}
        menuItems={[
          { key: 'map', label: '地图总览', icon: '🗺️', active: true },
          { key: 'fields', label: '我的田块', icon: '🌾' },
          { key: 'records', label: '灌溉记录', icon: '📋' },
        ]}
        activeMenu="map"
        onMenuClick={(key) => {
          if (key === 'map') navigate('/dashboard')
          else if (key === 'fields') navigate('/dashboard/fields')
          else navigate('/dashboard/fields')
        }}
        panelItems={panelItems}
        tools={[
          { label: '定位当前位置', primary: true },
          { label: '自动识别田块', onClick: () => {
            fetch('/api/fields/nearby?lat=30.26&lng=120.17')
              .then(r => r.json())
              .then(setNearbyFields)
          }},
          { label: '手动框选' },
          { label: '绑定到账号', onClick: () => {
            if (selectedField && !selectedField.ownerId) {
              setShowBindDialog(true)
            }
          }},
        ]}
      >
        <MapView
          fields={nearbyFields}
          selectedFieldId={selectedField?.id}
          onFieldClick={handleFieldSelect}
        />

        {showBindDialog && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-50">
            <div className="bg-[#131820] border border-[#1e2430] rounded-lg p-6 w-80">
              <h3 className="text-sm font-semibold text-[#c8ccd0] mb-4">绑定田块 {selectedField?.name}</h3>
              <div className="flex flex-col gap-3">
                <div>
                  <label className="text-[10px] text-[#6b7280]">作物种类</label>
                  <input value={crop} onChange={e => setCrop(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1"
                    placeholder="如: 小麦" />
                </div>
                <div>
                  <label className="text-[10px] text-[#6b7280]">生长周期</label>
                  <input value={growthStage} onChange={e => setGrowthStage(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1"
                    placeholder="如: 拔节期" />
                </div>
                <div>
                  <label className="text-[10px] text-[#6b7280]">播种日期</label>
                  <input type="date" value={plantDate} onChange={e => setPlantDate(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1" />
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                <button onClick={() => setShowBindDialog(false)}
                  className="flex-1 py-1.5 text-xs border border-[#1e2430] text-[#9ca3af] rounded-md">取消</button>
                <button onClick={handleBind}
                  className="flex-1 py-1.5 text-xs bg-[#818cf8] text-white rounded-md">确认绑定</button>
              </div>
            </div>
          </div>
        )}
      </Layout>
    </MapProvider>
  )
}
