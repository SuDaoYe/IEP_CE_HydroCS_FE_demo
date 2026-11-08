import { useState } from 'react'
import { api } from '../lib/api'
import type { EtForecastResult } from '../types'
import { SectionTitle, Spinner } from './ui'

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
      <SectionTitle right={<span className="hc-chip text-[var(--hc-accent)]">历史演示</span>}>
        蒸散发模型预测
      </SectionTitle>
      <p className="mb-2 text-[11px] leading-relaxed text-[var(--hc-muted)]">
        随机森林用前 60 天气象预测单日实际蒸散发（ETMonitor 口径）。灌溉需水量另行计算。
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
        <div role="status" className="mt-3 rounded-lg border border-[var(--hc-line)] px-2.5 py-2">
          <p className="text-[11px] text-[var(--hc-muted)]">{result.date} · 预测日蒸散发</p>
          <p className="hc-num text-xl text-[var(--hc-accent)]">
            {result.et_mm_day.toFixed(2)} <span className="text-xs">mm/天</span>
          </p>
          <p className="text-[10px] text-[var(--hc-faint)]">
            气象历史 {result.history_start} 至 {result.history_end} · {result.cells} 个网格
          </p>
        </div>
      )}
    </section>
  )
}
