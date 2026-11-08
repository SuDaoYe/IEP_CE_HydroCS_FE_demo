import { useState } from 'react'
import { api } from '../lib/api'
import { fmtDate, fmtM3, fmtMm, fmtNumber } from '../lib/format'
import type { EtForecastPeriod, EtForecastResult } from '../types'
import { SectionTitle, Spinner } from './ui'

const PERIODS = [
  { key: 'day', label: '所选当天' },
  { key: 'week', label: '后 7 天' },
  { key: 'month', label: '后 30 天' },
] as const

function PeriodResult({ label, period }: { label: string; period: EtForecastPeriod }) {
  const full = period.et_days === period.days && period.irrigation_days === period.days
  return (
    <article aria-label={label} className="rounded-lg border border-[var(--hc-line)] px-2.5 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <h3 className="text-[12px] font-medium text-[var(--hc-ink)]">{label}</h3>
        <span className="text-[10px] text-[var(--hc-muted)]">
          {fmtDate(period.start)}{period.days > 1 && ` 至 ${fmtDate(period.end)}`}
        </span>
      </div>
      <p className="mt-0.5 text-[11px] text-[var(--hc-muted)]">预测蒸散 {fmtMm(period.et_mm)}</p>
      <dl className="mt-1 grid grid-cols-2 gap-2">
        <div>
          <dt className="text-[10px] text-[var(--hc-muted)]">净补水</dt>
          <dd className="hc-num text-[16px] text-[var(--hc-sky)]">{fmtM3(period.net_volume_m3)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-[var(--hc-muted)]">毛供水（含损失）</dt>
          <dd className="hc-num text-[16px] text-[var(--hc-accent)]">{fmtM3(period.gross_volume_m3)}</dd>
        </div>
      </dl>
      <p className="mt-1 text-[10px] text-[var(--hc-faint)]">
        {period.method === 'period-lstm' ? (period.days === 7 ? '周尺度 LSTM' : '月尺度 LSTM') : '日尺度 LSTM'}
        {' · 气象输入 '}{fmtDate(period.history_start)} 至 {fmtDate(period.history_end)}
      </p>
      {!full && (
        <p className="mt-1 text-[10px] text-[var(--hc-amber)]">
          仅累计有数据的日期 · 蒸散 {period.et_days}/{period.days} 天 · 补水 {period.irrigation_days}/{period.days} 天
        </p>
      )}
    </article>
  )
}

export default function EtForecast({ fieldId }: { fieldId: string }) {
  const [date, setDate] = useState('2004-07-15')
  const [result, setResult] = useState<EtForecastResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function runForecast() {
    setLoading(true)
    setResult(null)
    setError('')
    try {
      setResult(await api.etForecast(fieldId, date))
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3">
      <SectionTitle right={<span className="hc-chip text-[var(--hc-accent)]">2004 年演示</span>}>
        蒸散发模型预测
      </SectionTitle>
      <p className="mb-2 text-[11px] leading-relaxed text-[var(--hc-muted)]">
        所选当天用 60 天 LSTM。后 7 天和后 30 天用独立的周、月尺度 LSTM，只读所选日期之前的气象。
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
          {loading ? <><Spinner size={13} /> 预测中</> : '查看预测'}
        </button>
      </form>
      {error && <p role="alert" className="mt-2 text-[11px] text-[var(--hc-danger)]">{error}</p>}
      {result && (
        <div role="status" className="mt-3 space-y-2">
          {PERIODS.map(({ key, label }) => (
            <PeriodResult key={key} label={label} period={result.periods[key]} />
          ))}
          <p className="text-[10px] text-[var(--hc-faint)]">
            输入截至 {result.history_end} · {result.cells} 个网格 · η {fmtNumber(result.efficiency, 2)}
          </p>
          <details className="text-[10px] leading-relaxed text-[var(--hc-muted)]">
            <summary className="cursor-pointer">补水估算依据</summary>
            <p className="mt-1">
              当天补水用当天历史降雨。后 7 天和后 30 天用模型预测的有效降雨，逐日估算缺口并累计。水田计入渗漏。
            </p>
          </details>
        </div>
      )}
    </section>
  )
}
