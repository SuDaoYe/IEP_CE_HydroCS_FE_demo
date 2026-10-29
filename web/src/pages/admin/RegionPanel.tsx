import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { fmtNumber } from '../../lib/format'
import { useUI } from '../../store/ui'
import RegionPicker from '../../components/RegionPicker'
import { Empty, SectionTitle, Spinner, Stat } from '../../components/ui'
import type { RegionHit, RegionOverview, RegionSummary } from '../../types'

const LEVEL_LABEL: Record<string, string> = { province: '省级', city: '地级市', district: '区县' }

export default function RegionPanel({ days }: { days: number }) {
  const notify = useUI((state) => state.notify)
  const [overview, setOverview] = useState<RegionOverview | null>(null)
  const [picked, setPicked] = useState<RegionHit | null>(null)
  const [summary, setSummary] = useState<RegionSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        setOverview(await api.adminRegionOverview(days))
      } catch (error) {
        notify((error as Error).message, 'error')
      } finally {
        setLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days])

  async function load(code: string, label: string) {
    setBusy(true)
    try {
      const payload = await api.adminRegionSummary(code, days)
      setSummary(payload)
      notify(`已统计 ${label}`)
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  function pick(hit: RegionHit) {
    setPicked(hit)
    void load(hit.adcode, hit.fullname)
  }

  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle
          right={
            overview?.divisions.available ? (
              <span className="hc-chip">{overview.regions.length} 个行政区有数据</span>
            ) : (
              <span className="hc-chip border-[var(--hc-amber)]/50 text-[var(--hc-amber)]">行政区库未生成</span>
            )
          }
        >
          选择行政区
        </SectionTitle>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <RegionPicker onPick={pick} className="w-full sm:max-w-[420px]" />
          {busy && <Spinner size={14} />}
          {picked && <span className="hc-chip shrink-0">{LEVEL_LABEL[picked.level] ?? picked.level}</span>}
        </div>
        <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
          省级选择会自动汇总下辖地级市；田块按中心点落区，边界附近约 1 km 误差。
        </p>
      </section>

      {/* cities that currently hold parcels */}
      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle>已有田块的行政区</SectionTitle>
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[11px] text-[var(--hc-faint)]">
            <Spinner size={13} /> 汇总中…
          </div>
        ) : overview && overview.regions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-[11.5px]">
              <thead className="text-[var(--hc-faint)]">
                <tr>
                  <th className="py-1.5 text-left font-medium">行政区</th>
                  <th className="py-1.5 text-right font-medium">田块</th>
                  <th className="py-1.5 text-right font-medium">用水户</th>
                  <th className="py-1.5 text-right font-medium">面积</th>
                  <th className="py-1.5 text-right font-medium">{days} 天需水</th>
                  <th className="py-1.5 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {overview.regions.map((row) => (
                  <tr key={row.adcode} className="border-t border-[var(--hc-line)]">
                    <td className="py-1.5 text-[var(--hc-ink)]">
                      {row.fullname}
                      <span className="ml-1 text-[10px] text-[var(--hc-faint)]">{row.adcode}</span>
                    </td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">{row.fields}</td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">{row.users}</td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">
                      {fmtNumber(row.area_mu, 1)} 亩
                    </td>
                    <td className="hc-num py-1.5 text-right text-[var(--hc-accent)]">
                      {fmtNumber(row.volume_m3, 0)} m³
                    </td>
                    <td className="py-1.5 text-right">
                      {row.adcode !== '__unassigned__' && (
                        <button
                          type="button"
                          onClick={() =>
                            pick({
                              adcode: row.adcode,
                              name: row.name,
                              fullname: row.fullname,
                              level: 'city',
                              parent: null,
                              lon: null,
                              lat: null,
                              score: 0,
                              has_geometry: true,
                            })
                          }
                          className="text-[10.5px] text-[var(--hc-sky)]"
                        >
                          查看
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon="fields" title="还没有田块落在已收录的行政区里" />
        )}
        {overview && overview.unmatched > 0 && (
          <p className="mt-2 text-[10.5px] text-[var(--hc-amber)]">
            有 {overview.unmatched} 块田未能匹配行政区（坐标可能在简化边界之外）。
          </p>
        )}
      </section>

      {/* summary */}
      {summary && (
        <>
          <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
            <SectionTitle
              right={
                <span className="text-[10px] text-[var(--hc-faint)]">
                  生成于 {summary.generated_at.slice(11, 16)}
                </span>
              }
            >
              {summary.region.fullname} · 整体需水
            </SectionTitle>
            <div className="grid grid-cols-2 gap-2.5 md:grid-cols-5">
              <Stat
                label={`${days} 天需灌（净）`}
                value={fmtNumber(summary.totals.net_volume_m3 ?? summary.totals.volume_m3, 0)}
                unit="m³"
                accent
                size="lg"
              />
              <Stat
                label={`${days} 天总水量（毛）`}
                value={fmtNumber(summary.totals.volume_m3, 0)}
                unit="m³"
                size="lg"
              />
              <Stat label="日均供水" value={fmtNumber(summary.totals.daily_m3, 1)} unit="m³/天" size="sm" />
              <Stat label="田块 / 用水户" value={`${summary.totals.fields} / ${summary.totals.users}`} size="sm" />
              <Stat label="覆盖面积" value={fmtNumber(summary.totals.area_mu, 1)} unit="亩" size="sm" />
            </div>
            <p className="mt-2 text-[9.5px] text-[var(--hc-faint)]">
              净 = 作物需要补进根区的水量；毛 = 计入灌溉水利用系数后从水源实际取的水量
            </p>

            {summary.by_date.length > 0 && (
              <div className="mt-3 flex flex-col gap-1">
                {summary.by_date.slice(0, days).map((row) => {
                  const max = Math.max(...summary.by_date.map((item) => item.volume_m3), 1)
                  return (
                    <div key={row.date} className="flex items-center gap-2">
                      <span className="w-14 shrink-0 text-[10px] text-[var(--hc-faint)]">{row.date.slice(5)}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--hc-canvas)]">
                        <div
                          className="h-full rounded-full bg-[var(--hc-accent)]/85"
                          style={{ width: `${(row.volume_m3 / max) * 100}%` }}
                        />
                      </div>
                      <span className="hc-num w-16 shrink-0 text-right text-[10px] text-[var(--hc-ink)]">
                        {fmtNumber(row.volume_m3, 0)} m³
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <div className="grid gap-3 lg:grid-cols-2">
            <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
              <SectionTitle>用水户需水统计</SectionTitle>
              {summary.users.length ? (
                <table className="w-full text-[11.5px]">
                  <thead className="text-[var(--hc-faint)]">
                    <tr>
                      <th className="py-1 text-left font-medium">用户</th>
                      <th className="py-1 text-right font-medium">田块</th>
                      <th className="py-1 text-right font-medium">面积</th>
                      <th className="py-1 text-right font-medium">需水</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.users.map((user) => (
                      <tr key={user.user_id} className="border-t border-[var(--hc-line)]">
                        <td className="py-1.5 text-[var(--hc-ink)]">{user.name}</td>
                        <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">{user.fields}</td>
                        <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">
                          {fmtNumber(user.area_mu, 1)} 亩
                        </td>
                        <td className="hc-num py-1.5 text-right text-[var(--hc-accent)]">
                          {fmtNumber(user.volume_m3, 0)} m³
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty icon="users" title="该区域还没有注册用户录入田块" />
              )}
            </section>

            <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
              <SectionTitle>下辖行政区分解</SectionTitle>
              {summary.cities.length ? (
                <ul className="flex flex-col">
                  {summary.cities.map((city) => (
                    <li
                      key={city.adcode}
                      className="flex items-center gap-2 border-b border-[var(--hc-line)] py-1.5 text-[11.5px] last:border-0"
                    >
                      <span className="text-[var(--hc-ink)]">{city.name}</span>
                      <span className="hc-chip">{city.fields} 块</span>
                      <span className="hc-num ml-auto text-[var(--hc-accent)]">
                        {fmtNumber(city.volume_m3, 0)} m³
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty icon="info" title="没有更细一级的数据" />
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {summary.crop_mix.map((crop) => (
                  <span key={crop.crop} className="hc-chip">
                    {crop.crop} {fmtNumber(crop.area_mu, 1)} 亩
                  </span>
                ))}
              </div>
            </section>
          </div>

          <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
            <SectionTitle>田块明细（最多 120 条）</SectionTitle>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-[11.5px]">
                <thead className="text-[var(--hc-faint)]">
                  <tr>
                    <th className="py-1.5 text-left font-medium">田块</th>
                    <th className="py-1.5 text-left font-medium">归属用户</th>
                    <th className="py-1.5 text-left font-medium">作物</th>
                    <th className="py-1.5 text-right font-medium">面积</th>
                    <th className="py-1.5 text-right font-medium">需水</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.fields.map((field) => (
                    <tr key={field.id} className="border-t border-[var(--hc-line)]">
                      <td className="py-1.5 text-[var(--hc-ink)]">{field.name}</td>
                      <td className="py-1.5 text-[var(--hc-muted)]">{field.owner_name}</td>
                      <td className="py-1.5 text-[var(--hc-muted)]">{field.crop_label ?? '未录入'}</td>
                      <td className="hc-num py-1.5 text-right text-[var(--hc-muted)]">
                        {fmtNumber(field.area_mu, 1)} 亩
                      </td>
                      <td className="hc-num py-1.5 text-right text-[var(--hc-accent)]">
                        {fmtNumber(field.volume_m3, 0)} m³
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-2 list-disc pl-4 text-[10px] leading-relaxed text-[var(--hc-faint)]">
              {summary.assumptions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}
