import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { fmtDate, fmtMu, fmtM3, fmtNumber } from '../lib/format'
import { editGeometry } from '../lib/actions'
import { useData } from '../store/data'
import { useIrrigation } from '../store/irrigation'
import { useUI } from '../store/ui'
import { flyToField } from './mapBridge'
import IrrigationChart from './IrrigationChart'
import { Empty, Icon, SectionTitle, Spinner, Stat } from './ui'
import type { Crop, WaterBucket } from '../types'

/** Weekly / monthly cumulative water demand as a ranked bar list. */
function BucketList({ buckets, unitLabel }: { buckets: WaterBucket[]; unitLabel: string }) {
  if (!buckets.length) {
    return <div className="py-6 text-center text-[10.5px] text-[var(--hc-faint)]">暂无数据</div>
  }
  const max = Math.max(...buckets.map((bucket) => bucket.volume_m3), 1)
  return (
    <div className="flex flex-col gap-1.5">
      {buckets.map((bucket) => (
        <div key={`${bucket.label}-${bucket.start}`} className="flex items-center gap-2">
          <span className="w-[58px] shrink-0 text-[10px] text-[var(--hc-muted)]">
            {unitLabel === '月' ? bucket.label.slice(2) + '月' : bucket.label}
          </span>
          <span className="w-[80px] shrink-0 text-[9.5px] text-[var(--hc-faint)]">
            {bucket.start.slice(5)}→{bucket.end.slice(5)}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--hc-canvas)]">
            <div
              className="h-full rounded-full bg-[var(--hc-accent)]/85"
              style={{ width: `${(bucket.volume_m3 / max) * 100}%` }}
            />
          </div>
          <span className="shrink-0 text-right leading-tight">
            <span className="hc-num block text-[11px] text-[var(--hc-ink)]">
              {bucket.volume_m3 >= 1000
                ? `${fmtNumber(bucket.volume_m3 / 1000, 2)}k`
                : fmtNumber(bucket.volume_m3, 0)}
              <span className="ml-0.5 text-[8.5px] text-[var(--hc-faint)]">毛</span>
            </span>
            <span className="hc-num block text-[9.5px] text-[var(--hc-sky)]">
              {bucket.net_volume_m3 !== undefined && bucket.net_volume_m3 !== null
                ? bucket.net_volume_m3 >= 1000
                  ? `${fmtNumber(bucket.net_volume_m3 / 1000, 2)}k`
                  : fmtNumber(bucket.net_volume_m3, 0)
                : '—'}
              <span className="ml-0.5 text-[8.5px] text-[var(--hc-faint)]">净</span>
            </span>
          </span>
          <span className="w-[46px] shrink-0 text-right text-[9px] text-[var(--hc-faint)]">
            {bucket.days}天
          </span>
        </div>
      ))}
      <div className="mt-0.5 flex justify-end gap-3 text-[9px] text-[var(--hc-faint)]">
        <span>
          净 = 需要灌溉的水量（补进根区）
        </span>
        <span>毛 = 总水量（含输水损失）</span>
      </div>
    </div>
  )
}

export default function DetailPanel() {
  const fields = useData((state) => state.fields)
  const selectedId = useData((state) => state.selectedId)
  const patchField = useData((state) => state.patchField)
  const removeField = useData((state) => state.removeField)
  const detailOpen = useUI((state) => state.detailOpen)
  const setDetailOpen = useUI((state) => state.setDetailOpen)
  const notify = useUI((state) => state.notify)

  const plan = useIrrigation((state) => state.plan)
  const planLoading = useIrrigation((state) => state.planLoading)
  const loadPlan = useIrrigation((state) => state.loadPlan)
  const days = useIrrigation((state) => state.days)
  const setDays = useIrrigation((state) => state.setDays)

  const [crops, setCrops] = useState<Crop[]>([])
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState<'day' | 'week' | 'month'>('day')

  const field = useMemo(() => fields.find((item) => item.id === selectedId) ?? null, [fields, selectedId])

  useEffect(() => {
    api.crops().then(setCrops).catch(() => setCrops([]))
  }, [])

  useEffect(() => {
    void loadPlan(field?.id ?? null, days)
  }, [field?.id, days, loadPlan])

  useEffect(() => {
    setEditing(false)
  }, [field?.id])

  const cropSpec = crops.find((crop) => crop.key === field?.crop)

  // 合计数字必须带时间尺度，所以把区间拼成一句可读的文案
  const windowRange = plan
    ? `${fmtDate(plan.window.start)} → ${fmtDate(
        plan.series[plan.series.length - 1]?.date ?? plan.window.start,
      )}`
    : ''

  async function applyChange(patch: Record<string, unknown>) {
    if (!field) return
    setSaving(true)
    try {
      await patchField(field.id, patch)
      notify('已保存')
      void loadPlan(field.id, days)
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const content = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-[var(--hc-line)] px-3.5 py-2.5">
        <Icon name="info" size={15} className="text-[var(--hc-accent)]" />
        <span className="text-[12.5px] font-medium text-[var(--hc-ink)]">详细信息</span>
        <button
          type="button"
          onClick={() => setDetailOpen(false)}
          className="hc-btn ml-auto h-8 w-8 !min-h-0 !px-0 lg:hidden"
          aria-label="关闭详情"
        >
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 pb-4 pt-3">
        {!field ? (
          <Empty icon="target" title="未选择田块" hint="点地图上的绿色田块，或在下方列表里选一块。" />
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-[15px] font-semibold leading-tight text-[var(--hc-ink)]">{field.name}</h2>
                  <p className="mt-0.5 text-[11px] text-[var(--hc-faint)]">
                    {field.source === 'segment+edited'
                      ? '识别后手工修正'
                      : field.source === 'segment'
                        ? '模型识别'
                        : '手工绘制'}
                    {field.confidence ? ` · 置信度 ${(field.confidence * 100).toFixed(0)}%` : ''}
                  </p>
                </div>
                <span className="hc-chip">{fmtMu(field.area_mu)}</span>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-2 rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3">
                <Stat label="面积 m²" value={fmtNumber(field.area_m2, 0)} size="sm" />
                <Stat label="面积 亩" value={fmtNumber(field.area_mu, 2)} size="sm" />
                <Stat label="面积 ha" value={fmtNumber(field.area_ha, 3)} size="sm" />
              </div>
            </div>

            {/* crop + stage */}
            <div className="rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3">
              <SectionTitle
                right={
                  <button
                    type="button"
                    onClick={() => setEditing((value) => !value)}
                    className="text-[10.5px] text-[var(--hc-sky)]"
                  >
                    {editing ? '收起' : '修改'}
                  </button>
                }
              >
                作物与生育期
              </SectionTitle>

              {editing ? (
                <div className="flex flex-col gap-2">
                  <select
                    value={field.crop ?? ''}
                    onChange={(event) => void applyChange({ crop: event.target.value || null, stage_key: null })}
                    className="hc-input"
                  >
                    <option value="">选择作物…</option>
                    {crops.map((crop) => (
                      <option key={crop.key} value={crop.key}>
                        {crop.label}
                        {crop.paddy ? '（水田）' : ''}
                      </option>
                    ))}
                  </select>
                  <select
                    value={field.stage_key ?? ''}
                    onChange={(event) => void applyChange({ stage_key: event.target.value || null })}
                    className="hc-input"
                    disabled={!cropSpec}
                  >
                    <option value="">选择生育期…</option>
                    {cropSpec?.stages.map((stage) => (
                      <option key={stage.key} value={stage.key}>
                        {stage.label} · Kc {stage.kc.toFixed(2)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    value={field.plant_date ?? ''}
                    onChange={(event) => void applyChange({ plant_date: event.target.value || null })}
                    className="hc-input"
                  />
                  {saving && <span className="text-[10px] text-[var(--hc-faint)]">保存中…</span>}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-y-2">
                  <Stat label="作物" value={field.crop_label ?? '未录入'} size="sm" />
                  <Stat label="生育期" value={field.stage_label ?? '—'} size="sm" />
                  <Stat label="系数 Kc" value={field.kc ? field.kc.toFixed(2) : '—'} size="sm" />
                  <Stat
                    label="播种日期"
                    value={field.plant_date ? fmtDate(field.plant_date) : '—'}
                    size="sm"
                  />
                </div>
              )}
            </div>

            {/* irrigation */}
            <div className="rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3">
              <SectionTitle
                right={
                  <div className="flex items-center gap-1">
                    {[7, 30, 90].map((span) => (
                      <button
                        key={span}
                        type="button"
                        onClick={() => setDays(span)}
                        className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                          days === span
                            ? 'bg-[var(--hc-accent)]/16 text-[var(--hc-accent)]'
                            : 'text-[var(--hc-faint)]'
                        }`}
                      >
                        {span} 天
                      </button>
                    ))}
                  </div>
                }
              >
                灌溉需水量
              </SectionTitle>

              {planLoading ? (
                <div className="flex items-center justify-center gap-2 py-8 text-[11px] text-[var(--hc-faint)]">
                  <Spinner size={13} /> 正在解算…
                </div>
              ) : plan ? (
                <div className="flex flex-col gap-3">
                  {plan.method && (
                    <div className="flex items-center gap-1.5 text-[10px] text-[var(--hc-faint)]">
                      <span className="hc-chip border-[var(--hc-accent)]/40 text-[var(--hc-accent)]">
                        {plan.method === 'era5-pm' ? 'ERA5 · FAO-56' : 'ETMonitor 近似'}
                      </span>
                      期间降雨 {fmtNumber(plan.totals.rain_mm ?? 0, 1)} mm ·
                      有效 {fmtNumber(plan.totals.pe_mm ?? 0, 1)} mm
                    </div>
                  )}
                  <div className="flex items-center gap-1.5">
                    {(
                      [
                        ['day', '日'],
                        ['week', '周'],
                        ['month', '月'],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setView(key)}
                        className={`flex-1 rounded-md border px-2 py-1 text-[10.5px] transition ${
                          view === key
                            ? 'border-[var(--hc-accent)]/50 bg-[var(--hc-accent)]/12 text-[var(--hc-accent)]'
                            : 'border-[var(--hc-line)] text-[var(--hc-faint)]'
                        }`}
                      >
                        {label}尺度
                      </button>
                    ))}
                  </div>

                  {/* 时间尺度必须写在数字旁边：这是“X 天合计”，不是当天值 */}
                  <div className="rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface)] px-2 py-1.5">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-[var(--hc-muted)]">
                        统计区间 <span className="hc-num text-[var(--hc-ink)]">{windowRange}</span>
                      </span>
                      <span className="hc-chip border-[var(--hc-accent)]/50 text-[var(--hc-accent)]">
                        共 {plan.window.days} 天合计
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-[var(--hc-sky)]/40 bg-[var(--hc-sky)]/8 p-2">
                      <div className="text-[9.5px] leading-tight text-[var(--hc-sky)]">
                        需要灌溉的水量（净）
                        <span className="ml-1 rounded bg-[var(--hc-sky)]/14 px-1 py-0.5 text-[8.5px]">
                          {plan.window.days} 天
                        </span>
                      </div>
                      <div className="hc-num mt-0.5 text-[18px] font-semibold leading-tight text-[var(--hc-sky)]">
                        {fmtM3(plan.totals.net_volume_m3 ?? plan.totals.volume_m3)}
                      </div>
                      <div className="mt-0.5 text-[9px] text-[var(--hc-faint)]">
                        {fmtNumber(plan.totals.net_mm, 1)} mm
                        {plan.totals.per_mu_net_m3 != null
                          ? ` · ${fmtNumber(plan.totals.per_mu_net_m3, 1)} m³/亩`
                          : ''}
                      </div>
                    </div>
                    <div className="rounded-lg border border-[var(--hc-accent)]/40 bg-[var(--hc-accent)]/8 p-2">
                      <div className="text-[9.5px] leading-tight text-[var(--hc-accent)]">
                        总水量（毛，含损失）
                        <span className="ml-1 rounded bg-[var(--hc-accent)]/14 px-1 py-0.5 text-[8.5px]">
                          {plan.window.days} 天
                        </span>
                      </div>
                      <div className="hc-num mt-0.5 text-[18px] font-semibold leading-tight text-[var(--hc-accent)]">
                        {fmtM3(plan.totals.gross_volume_m3 ?? plan.totals.volume_m3)}
                      </div>
                      <div className="mt-0.5 text-[9px] text-[var(--hc-faint)]">
                        {fmtNumber(plan.totals.gross_mm, 1)} mm
                        {plan.totals.per_mu_m3 != null
                          ? ` · ${fmtNumber(plan.totals.per_mu_m3, 1)} m³/亩`
                          : ''}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[9.5px] text-[var(--hc-faint)]">
                    <span>
                      日均需灌 {fmtM3(plan.totals.daily_avg_net_m3 ?? 0)} · 日均供水{' '}
                      {fmtM3(plan.totals.daily_avg_m3)}
                    </span>
                    <span>η = {fmtNumber(plan.params.efficiency, 2)}</span>
                  </div>

                  {view === 'day' && <IrrigationChart series={plan.series} />}
                  {view === 'week' && (
                    <BucketList buckets={plan.aggregates?.weekly ?? []} unitLabel="周" />
                  )}
                  {view === 'month' && (
                    <BucketList buckets={plan.aggregates?.monthly ?? []} unitLabel="月" />
                  )}

                  {view === 'day' && (
                  <div className="overflow-hidden rounded-lg border border-[var(--hc-line)]">
                    <table className="w-full text-[10.5px]">
                      <thead className="bg-[var(--hc-canvas)] text-[var(--hc-faint)]">
                        <tr>
                          <th className="px-2 py-1.5 text-left font-medium">日期</th>
                          <th className="px-2 py-1.5 text-right font-medium">ET0</th>
                          <th className="px-2 py-1.5 text-right font-medium">降雨</th>
                          <th className="px-2 py-1.5 text-right font-medium">需水 mm</th>
                          <th className="px-2 py-1.5 text-right font-medium">水量 m³</th>
                        </tr>
                      </thead>
                      <tbody className="hc-num">
                        {plan.series.map((day) => (
                          <tr key={day.date} className="border-t border-[var(--hc-line)]">
                            <td className="px-2 py-1.5 text-left text-[var(--hc-muted)]">{fmtDate(day.date)}</td>
                            <td className="px-2 py-1.5 text-right text-[var(--hc-faint)]">
                              {day.et0_mm.toFixed(2)}
                            </td>
                            <td className="px-2 py-1.5 text-right text-[var(--hc-sky)]">
                              {day.precip_mm ? day.precip_mm.toFixed(1) : '—'}
                            </td>
                            <td className="px-2 py-1.5 text-right text-[var(--hc-ink)]">{day.gross_mm.toFixed(2)}</td>
                            <td className="px-2 py-1.5 text-right text-[var(--hc-accent)]">{day.volume_m3.toFixed(1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  )}

                  <details className="text-[10px] text-[var(--hc-faint)]">
                    <summary className="cursor-pointer select-none">计算依据与假设</summary>
                    <ul className="mt-1.5 list-disc space-y-1 pl-4 leading-relaxed">
                      {plan.assumptions.map((line, index) => (
                        <li key={index}>{line}</li>
                      ))}
                    </ul>
                  </details>
                </div>
              ) : (
                <div className="py-6 text-center text-[11px] text-[var(--hc-faint)]">暂无解算结果</div>
              )}
            </div>

            {/* actions */}
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  flyToField(field)
                  setDetailOpen(false)
                  useUI.getState().setSheet('peek')
                }}
                className="hc-btn"
              >
                <Icon name="target" size={14} /> 地图定位
              </button>
              <button type="button" onClick={() => void editGeometry(field)} className="hc-btn">
                <Icon name="pencil" size={14} /> 改形状
              </button>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="hc-btn"
              >
                <Icon name="crop" size={14} /> 改作物
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!window.confirm(`确定删除「${field.name}」？`)) return
                  await removeField(field.id)
                  notify('已删除田块')
                  setDetailOpen(false)
                }}
                className="hc-btn !border-[var(--hc-danger)]/40 text-[var(--hc-danger)]"
              >
                <Icon name="trash" size={14} /> 删除
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )

  return (
    <>
      <aside className="z-20 hidden w-[340px] shrink-0 border-l border-[var(--hc-line)] bg-[var(--hc-surface)] lg:block">
        {content}
      </aside>

      {detailOpen && (
        <div className="absolute inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
            onClick={() => setDetailOpen(false)}
          />
          <div className="hc-rise absolute inset-x-0 bottom-0 top-[12dvh] overflow-hidden rounded-t-2xl border-t border-[var(--hc-line)] bg-[var(--hc-surface)]">
            {content}
          </div>
        </div>
      )}
    </>
  )
}
