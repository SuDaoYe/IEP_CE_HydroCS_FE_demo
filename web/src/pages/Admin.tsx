import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDateTime, fmtMu, fmtM3, fmtNumber } from '../lib/format'
import { useUI } from '../store/ui'
import { Empty, Icon, SectionTitle, Spinner, Stat } from '../components/ui'
import MeteoPanel from './admin/MeteoPanel'
import ParamPanel from './admin/ParamPanel'
import RegionPanel from './admin/RegionPanel'
import type { AdminStats, Field, HistoryLog, User } from '../types'

type Tab = 'overview' | 'region' | 'meteo' | 'data' | 'params'

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'overview', label: '概览', icon: 'map' },
  { key: 'region', label: '行政区需水', icon: 'fields' },
  { key: 'meteo', label: '气象数据', icon: 'layers' },
  { key: 'data', label: '用户与田块', icon: 'users' },
  { key: 'params', label: '模型参数', icon: 'settings' },
]

export default function Admin() {
  const notify = useUI((state) => state.notify)
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [fields, setFields] = useState<Field[]>([])
  const [logs, setLogs] = useState<HistoryLog[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    void (async () => {
      try {
        const [statsPayload, userPayload, fieldPayload, logPayload] = await Promise.all([
          api.adminStats(7),
          api.adminUsers(),
          api.adminFields(),
          api.adminLogs(),
        ])
        setStats(statsPayload)
        setUsers(userPayload)
        setFields(fieldPayload)
        setLogs(logPayload)
      } catch (error) {
        notify((error as Error).message, 'error')
      } finally {
        setLoading(false)
      }
    })()
  }, [notify])

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-[12px] text-[var(--hc-faint)]">
        <Spinner size={15} /> 正在汇总数据…
      </div>
    )
  }

  const maxMix = Math.max(...(stats?.crop_mix.map((item) => item.area_mu) ?? [1]), 1)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6">
      <div className="mx-auto max-w-[1080px]">
        <h1 className="text-[17px] font-semibold text-[var(--hc-ink)]">管理后台</h1>
        <p className="mt-1 text-[11.5px] text-[var(--hc-faint)]">
          用户、田块、行政区需水汇总、气象数据导入与模型参数
        </p>

        <div className="mt-3 flex gap-1 overflow-x-auto rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-1">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11.5px] transition ${
                tab === item.key
                  ? 'bg-[var(--hc-accent)]/14 text-[var(--hc-accent)]'
                  : 'text-[var(--hc-faint)] hover:text-[var(--hc-ink)]'
              }`}
            >
              <Icon name={item.icon} size={13} />
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'region' && (
          <div className="mt-3">
            <RegionPanel days={7} />
          </div>
        )}
        {tab === 'meteo' && (
          <div className="mt-3">
            <MeteoPanel />
          </div>
        )}

        {tab === 'overview' && (
          <>
        {/* KPI row */}
        <div className="mt-4 grid grid-cols-2 gap-2.5 md:grid-cols-4">
          {[
            { label: '注册用户', value: stats?.users ?? 0, hint: `农户 ${stats?.farmers ?? 0}` },
            { label: '田块总数', value: stats?.fields ?? 0, hint: `${fmtMu(stats?.total_area_mu ?? 0)}` },
            { label: '今日区域需水', value: fmtM3(stats?.daily_m3 ?? 0), hint: '按已录入作物解算', accent: true },
            { label: '7 天区域需水', value: fmtM3(stats?.week_m3 ?? 0), hint: `作物录入率 ${stats?.coverage_pct ?? 0}%` },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3">
              <Stat label={item.label} value={item.value} hint={item.hint} accent={item.accent} size="lg" />
            </div>
          ))}
        </div>

        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {/* crop mix */}
          <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
            <SectionTitle>作物结构（亩）</SectionTitle>
            {stats?.crop_mix.length ? (
              <div className="flex flex-col gap-1.5">
                {stats.crop_mix.map((item) => (
                  <div key={item.crop} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 text-[11px] text-[var(--hc-muted)]">{item.crop}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--hc-canvas)]">
                      <div
                        className="h-full rounded-full bg-[var(--hc-sky)]/80"
                        style={{ width: `${(item.area_mu / maxMix) * 100}%` }}
                      />
                    </div>
                    <span className="hc-num w-16 shrink-0 text-right text-[10.5px] text-[var(--hc-ink)]">
                      {fmtNumber(item.area_mu, 1)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty icon="crop" title="暂无作物数据" />
            )}
          </section>

          {/* service status */}
          <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
            <SectionTitle>服务状态</SectionTitle>
            <ul className="flex flex-col gap-2 text-[11.5px]">
              <li className="flex items-center gap-2">
                <Icon
                  name={stats?.segmentation.weights_present ? 'check' : 'info'}
                  size={13}
                  className={stats?.segmentation.weights_present ? 'text-[var(--hc-accent)]' : 'text-[var(--hc-amber)]'}
                />
                <span className="text-[var(--hc-muted)]">田块识别</span>
                <span className="hc-num ml-auto text-[var(--hc-ink)]">{stats?.segmentation.backend}</span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  name={stats?.era5?.available ? 'check' : 'info'}
                  size={13}
                  className={stats?.era5?.available ? 'text-[var(--hc-accent)]' : 'text-[var(--hc-amber)]'}
                />
                <span className="text-[var(--hc-muted)]">ERA5 气象 + FAO-56</span>
                <span className="hc-num ml-auto text-[var(--hc-ink)]">
                  {stats?.era5?.available
                    ? `${String(stats.era5.domain?.days ?? '')} 天`
                    : '未加载（退回近似法）'}
                </span>
              </li>
              <li className="flex items-center gap-2">
                <Icon
                  name={stats?.et_grid.available ? 'check' : 'info'}
                  size={13}
                  className={stats?.et_grid.available ? 'text-[var(--hc-accent)]' : 'text-[var(--hc-amber)]'}
                />
                <span className="text-[var(--hc-muted)]">ET 蒸散网格</span>
                <span className="hc-num ml-auto text-[var(--hc-ink)]">
                  {stats?.et_grid.available ? String(stats.et_grid.domain?.days ?? '') + ' 天' : '未加载'}
                </span>
              </li>
              {stats?.et_grid.domain && (
                <li className="rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-2 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
                  覆盖范围 lon {String(stats.et_grid.domain.west)}–{String(stats.et_grid.domain.east)} · lat{' '}
                  {String(stats.et_grid.domain.south)}–{String(stats.et_grid.domain.north)} ·{' '}
                  {String(stats.et_grid.domain.resolution_deg)}°
                </li>
              )}
              {stats?.segmentation.error && (
                <li className="rounded-lg border border-[var(--hc-amber)]/40 bg-[var(--hc-amber)]/8 p-2 text-[10.5px] text-[var(--hc-amber)]">
                  {stats.segmentation.error}
                </li>
              )}
            </ul>
          </section>
        </div>
          </>
        )}

        {/* params：系数按行政区继承（全局 → 省 → 市） */}
        {tab === 'params' && <ParamPanel />}

        {tab === 'data' && (
          <>
        {/* users */}
        <section className="mt-3 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle>用户</SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-[11.5px]">
              <thead className="text-[var(--hc-faint)]">
                <tr>
                  <th className="py-1.5 text-left font-medium">姓名</th>
                  <th className="py-1.5 text-left font-medium">用户名</th>
                  <th className="py-1.5 text-left font-medium">手机</th>
                  <th className="py-1.5 text-right font-medium">角色</th>
                  <th className="py-1.5 text-right font-medium">田块</th>
                  <th className="py-1.5 text-right font-medium">注册</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-t border-[var(--hc-line)]">
                    <td className="py-1.5 text-[var(--hc-ink)]">{user.name}</td>
                    <td className="hc-num py-1.5 text-[var(--hc-muted)]">{user.username}</td>
                    <td className="hc-num py-1.5 text-[var(--hc-muted)]">{user.phone ?? '—'}</td>
                    <td className="py-1.5 text-right">
                      <span
                        className={`hc-chip ${
                          user.role === 'admin' ? 'border-[var(--hc-amber)]/50 text-[var(--hc-amber)]' : ''
                        }`}
                      >
                        {user.role === 'admin' ? '管理员' : '农户'}
                      </span>
                    </td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">{user.field_count ?? 0}</td>
                    <td className="py-1.5 text-right text-[var(--hc-faint)]">{fmtDateTime(user.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* fields */}
        <section className="mt-3 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle>全部田块</SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-[11.5px]">
              <thead className="text-[var(--hc-faint)]">
                <tr>
                  <th className="py-1.5 text-left font-medium">田块</th>
                  <th className="py-1.5 text-left font-medium">归属</th>
                  <th className="py-1.5 text-left font-medium">作物</th>
                  <th className="py-1.5 text-right font-medium">面积</th>
                  <th className="py-1.5 text-right font-medium">来源</th>
                  <th className="py-1.5 text-right font-medium">更新</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field) => (
                  <tr key={field.id} className="border-t border-[var(--hc-line)]">
                    <td className="py-1.5 text-[var(--hc-ink)]">{field.name}</td>
                    <td className="py-1.5 text-[var(--hc-muted)]">{field.owner_name ?? field.owner_id}</td>
                    <td className="py-1.5 text-[var(--hc-muted)]">
                      {field.crop_label ?? '未录入'} · {field.stage_label ?? '—'}
                    </td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">
                      {fmtNumber(field.area_mu, 2)} 亩
                    </td>
                    <td className="py-1.5 text-right">
                      <span className="hc-chip">{field.source}</span>
                    </td>
                    <td className="py-1.5 text-right text-[var(--hc-faint)]">{fmtDateTime(field.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* logs */}
        <section className="mt-3 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle>最近解算</SectionTitle>
          {logs.length ? (
            <ul className="flex flex-col">
              {logs.map((log) => (
                <li key={log.id} className="flex items-center gap-2 border-b border-[var(--hc-line)] py-1.5 last:border-0 text-[11px]">
                  <span className="text-[var(--hc-ink)]">{log.field_name}</span>
                  <span className="text-[var(--hc-faint)]">{log.user_name}</span>
                  <span className="hc-chip mr-auto">{log.days} 天</span>
                  <span className="hc-num text-[var(--hc-accent)]">
                    {log.totals.volume_m3 ? fmtM3(log.totals.volume_m3) : '—'}
                  </span>
                  <span className="w-20 text-right text-[10px] text-[var(--hc-faint)]">
                    {fmtDateTime(log.computed_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon="history" title="暂无记录" />
          )}
        </section>
          </>
        )}

        <div className="h-8" />
      </div>
    </div>
  )
}
