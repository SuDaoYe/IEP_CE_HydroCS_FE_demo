import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { fmtDate, fmtM3, fmtMm, fmtNumber } from '../lib/format'
import type { EtForecastPeriod, EtForecastResult } from '../types'
import EtForecastChart, { type EtRangeKey } from './EtForecastChart'
import { SectionTitle, Spinner } from './ui'

const RANGES: Array<{ key: EtRangeKey; toggle: string; chart: string }> = [
  { key: 'day', toggle: '当日', chart: '当天' },
  { key: 'week', toggle: '后7天', chart: '后7天' },
  { key: 'month', toggle: '后30天', chart: '后30天' },
]

function methodLabel(period: EtForecastPeriod): string {
  if (period.method !== 'period-lstm') return '日尺度 LSTM'
  return period.days === 7 ? '周尺度 LSTM' : '后 7 天 + 月尺度 LSTM 第 8–30 天'
}

function coverageText(period: EtForecastPeriod): string | null {
  if (period.et_days === period.days && period.irrigation_days === period.days) return null
  return `仅累计有数据的日期 · 蒸散 ${period.et_days}/${period.days} 天 · 补水 ${period.irrigation_days}/${period.days} 天`
}

export default function EtForecast({ fieldId }: { fieldId: string }) {
  const [date, setDate] = useState('2004-07-15')
  const [result, setResult] = useState<EtForecastResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState<EtRangeKey>('day')

  const requestSeq = useRef(0)
  const currentField = useRef(fieldId)
  currentField.current = fieldId

  // 田块切换时立即作废旧请求并隐藏上一块地的预测。
  useEffect(() => {
    requestSeq.current += 1
    setResult(null)
    setError('')
    setLoading(false)
    setRange('day')
  }, [fieldId])

  const chartPoints = useMemo(
    () =>
      result
        ? RANGES.map((item) => ({
            key: item.key,
            label: item.chart,
            period: result.periods[item.key],
          }))
        : [],
    [result],
  )

  async function runForecast() {
    const requestId = ++requestSeq.current
    const requestedField = fieldId
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await api.etForecast(requestedField, date)
      if (requestId !== requestSeq.current || currentField.current !== requestedField) return
      setResult(data)
    } catch (caught) {
      if (requestId !== requestSeq.current || currentField.current !== requestedField) return
      setError((caught as Error).message)
    } finally {
      if (requestId === requestSeq.current && currentField.current === requestedField) {
        setLoading(false)
      }
    }
  }

  const period = result ? result.periods[range] : null
  const coverage = period ? coverageText(period) : null

  return (
    <section className="rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3">
      <SectionTitle right={<span className="hc-chip text-[var(--hc-accent)]">2004 年演示</span>}>
        蒸散发模型预测
      </SectionTitle>
      <p className="mb-2 text-[11px] leading-relaxed text-[var(--hc-muted)]">
        所选当天用 60 天 LSTM。周、月尺度只读所选日期之前的气象，直接估算累计补水；三个范围均为累计量。
      </p>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void runForecast()
        }}
      >
        <input
          type="date"
          aria-label="蒸散发预测日期"
          className="hc-input min-w-0 flex-1"
          value={date}
          min="2004-01-01"
          max="2004-12-31"
          required
          disabled={loading}
          onChange={(event) => {
            setDate(event.target.value)
            setResult(null)
            setError('')
          }}
        />
        <button type="submit" className="hc-btn hc-btn-primary shrink-0" disabled={loading || !date}>
          {loading ? (
            <>
              <Spinner size={13} /> 预测中
            </>
          ) : (
            '查看预测'
          )}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-2 text-[11px] text-[var(--hc-danger)]">
          {error}
        </p>
      )}

      {loading && (
        <div
          role="status"
          className="mt-3 flex items-center justify-center gap-2 py-8 text-[11px] text-[var(--hc-faint)]"
        >
          <Spinner size={13} /> 正在解算…
        </div>
      )}

      {!loading && !result && !error && (
        <div className="mt-2 rounded-lg border border-dashed border-[var(--hc-line)] px-2.5 py-3 text-center text-[10px] leading-relaxed text-[var(--hc-faint)]">
          选择日期并点击「查看预测」。当天、后 7 天、后 30 天分别给出累计量。
        </div>
      )}

      {!loading && result && period && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-1.5" role="group" aria-label="预测范围">
            {RANGES.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={range === item.key}
                onClick={() => setRange(item.key)}
                className={`flex-1 rounded-md border px-1 py-1 text-[10.5px] transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--hc-accent)] ${
                  range === item.key
                    ? 'border-[var(--hc-accent)]/50 bg-[var(--hc-accent)]/12 text-[var(--hc-accent)]'
                    : 'border-[var(--hc-line)] text-[var(--hc-faint)] hover:text-[var(--hc-muted)]'
                }`}
              >
                {item.toggle}
              </button>
            ))}
          </div>

          <div className="rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface)] px-2 py-1.5">
            <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[10px]">
              <span className="text-[var(--hc-muted)]">
                统计区间{' '}
                <span className="hc-num text-[var(--hc-ink)]">
                  {fmtDate(period.start)} → {fmtDate(period.end)}
                </span>
              </span>
              <span className="hc-chip border-[var(--hc-accent)]/50 text-[9px] text-[var(--hc-accent)]">
                {period.days === 1 ? '当日值' : `共 ${period.days} 天合计`}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-[8.5px] text-[var(--hc-faint)]">
              <span>
                气象历史{' '}
                <span className="hc-num">
                  {fmtDate(period.history_start)} 至 {fmtDate(period.history_end)}
                </span>
              </span>
              <span>{methodLabel(period)}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 rounded-lg border border-[var(--hc-amber)]/30 bg-[var(--hc-amber)]/6 px-2 py-1.5">
            <div className="min-w-0">
              <div className="text-[9.5px] text-[var(--hc-muted)]">预测蒸散发</div>
              <div className="mt-0.5 text-[8.5px] text-[var(--hc-faint)]">
                蒸散有效 {period.et_days}/{period.days} 天
              </div>
            </div>
            <div className="hc-num shrink-0 text-[16px] font-semibold leading-tight text-[var(--hc-amber)]">
              {fmtMm(period.et_mm)}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="min-w-0 rounded-lg border border-[var(--hc-sky)]/40 bg-[var(--hc-sky)]/8 p-2">
              <div className="text-[9.5px] leading-tight text-[var(--hc-sky)]">
                需要灌溉的水量（净）
                <span className="ml-1 rounded bg-[var(--hc-sky)]/14 px-1 py-0.5 text-[8.5px]">
                  {period.days} 天
                </span>
              </div>
              <div className="hc-num mt-0.5 text-[18px] font-semibold leading-tight text-[var(--hc-sky)]">
                {fmtM3(period.net_volume_m3)}
              </div>
              <div className="mt-0.5 text-[8.5px] text-[var(--hc-faint)]">
                {period.net_volume_m3 === null
                  ? '无可用数值'
                  : `日均 ${fmtM3(period.net_volume_m3 / period.days)}`}
              </div>
            </div>
            <div className="min-w-0 rounded-lg border border-[var(--hc-accent)]/40 bg-[var(--hc-accent)]/8 p-2">
              <div className="text-[9.5px] leading-tight text-[var(--hc-accent)]">
                总水量（毛，含损失）
                <span className="ml-1 rounded bg-[var(--hc-accent)]/14 px-1 py-0.5 text-[8.5px]">
                  {period.days} 天
                </span>
              </div>
              <div className="hc-num mt-0.5 text-[18px] font-semibold leading-tight text-[var(--hc-accent)]">
                {fmtM3(period.gross_volume_m3)}
              </div>
              <div className="mt-0.5 text-[8.5px] text-[var(--hc-faint)]">
                {period.gross_volume_m3 === null
                  ? '无可用数值'
                  : `日均 ${fmtM3(period.gross_volume_m3 / period.days)}`}
              </div>
            </div>
          </div>

          {coverage && (
            <p className="text-[9.5px] leading-relaxed text-[var(--hc-amber)]">{coverage}</p>
          )}

          <EtForecastChart points={chartPoints} selected={range} onSelect={setRange} />

          <div>
            <div className="mb-1 flex items-center justify-between text-[8.5px] text-[var(--hc-faint)]">
              <span>预测结果对照</span>
              <span>各范围累计量</span>
            </div>
            <div className="overflow-hidden rounded-lg border border-[var(--hc-line)]">
              <table className="w-full table-fixed text-[9.5px]">
                <thead className="bg-[var(--hc-canvas)] text-[var(--hc-faint)]">
                  <tr>
                    <th className="w-[52px] px-1.5 py-1 text-left font-medium">范围</th>
                    <th className="px-1.5 py-1 text-right font-medium">蒸散 mm</th>
                    <th className="px-1.5 py-1 text-right font-medium">净补水 m³</th>
                    <th className="px-1.5 py-1 text-right font-medium">毛供水 m³</th>
                  </tr>
                </thead>
                <tbody className="hc-num">
                  {RANGES.map((item) => {
                    const row = result.periods[item.key]
                    return (
                      <tr
                        key={item.key}
                        className={`border-t border-[var(--hc-line)] ${
                          range === item.key ? 'bg-[var(--hc-accent)]/6' : ''
                        }`}
                      >
                        <td className="px-1.5 py-1 text-left text-[var(--hc-muted)]">{item.chart}</td>
                        <td className="px-1.5 py-1 text-right text-[var(--hc-amber)]">
                          {fmtNumber(row.et_mm, 2)}
                        </td>
                        <td className="px-1.5 py-1 text-right text-[var(--hc-sky)]">
                          {fmtNumber(row.net_volume_m3, 1)}
                        </td>
                        <td className="px-1.5 py-1 text-right text-[var(--hc-accent)]">
                          {fmtNumber(row.gross_volume_m3, 1)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[9px] text-[var(--hc-faint)]">
            输入截至 {result.history_end} · {result.cells} 个网格 · η{' '}
            {fmtNumber(result.efficiency, 2)}
          </p>

          <details className="text-[10px] leading-relaxed text-[var(--hc-muted)]">
            <summary className="cursor-pointer select-none">补水估算依据与气象历史</summary>
            <p className="mt-1">
              当天补水用当天历史降雨。周、月模型以历史逐日缺口的累计值为训练目标，预测时直接估算累计净补水。
              后 30 天合计采用后 7 天结果和第 8–30 天的月尺度估算。水田计入渗漏。各范围的蒸散与气象历史范围见上方区间条。
            </p>
          </details>
        </div>
      )}
    </section>
  )
}
