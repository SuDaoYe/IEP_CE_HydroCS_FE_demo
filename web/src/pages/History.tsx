import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDateTime, fmtMm, fmtM3, fmtNumber, relativeTime } from '../lib/format'
import { useIrrigation } from '../store/irrigation'
import { Empty, Icon, SectionTitle, Spinner, Stat } from '../components/ui'
import IrrigationChart from '../components/IrrigationChart'
import type { HistoryLog, IrrigationDay } from '../types'

export default function History() {
  const summary = useIrrigation((state) => state.summary)
  const loadSummary = useIrrigation((state) => state.loadSummary)
  const [logs, setLogs] = useState<HistoryLog[]>([])
  const [loading, setLoading] = useState(true)
  const [activeField, setActiveField] = useState<string | null>(null)

  useEffect(() => {
    void loadSummary(15)
    api
      .logs(60)
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false))
  }, [loadSummary])

  const selectedSeries: IrrigationDay[] | null =
    summary?.fields.find((entry) => entry.field.id === activeField)?.series ?? null

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6">
      <div className="mx-auto max-w-[980px]">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[17px] font-semibold text-[var(--hc-ink)]">灌溉记录</h1>
            <p className="mt-1 text-[11.5px] text-[var(--hc-faint)]">
              逐日蒸散与需水解算、历次查询记录
            </p>
          </div>
          <div className="flex gap-5">
            <Stat label="半个月需水" value={fmtM3(summary?.totals.week_m3 ?? 0)} accent size="sm" />
            <Stat label="解算田块" value={summary?.totals.fields ?? 0} size="sm" />
          </div>
        </div>

        {/* 15-day forecast across fields */}
        <section className="mt-4 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle
            right={
              summary?.fields.length ? (
                <select
                  value={activeField ?? ''}
                  onChange={(event) => setActiveField(event.target.value || null)}
                  className="hc-input h-8 w-auto text-[11px]"
                >
                  <option value="">全部田块合计</option>
                  {summary.fields.map((entry) => (
                    <option key={entry.field.id} value={entry.field.id}>
                      {entry.field.name}
                    </option>
                  ))}
                </select>
              ) : null
            }
          >
            未来 15 天需水曲线
          </SectionTitle>

          {selectedSeries ? (
            <IrrigationChart series={selectedSeries} height={130} />
          ) : summary?.totals.by_date.length ? (
            <div className="flex flex-col gap-1.5">
              {summary.totals.by_date.slice(0, 15).map((day) => {
                const max = Math.max(...summary.totals.by_date.map((item) => item.volume_m3), 1)
                return (
                  <div key={day.date} className="flex items-center gap-2">
                    <span className="w-14 shrink-0 text-[10.5px] text-[var(--hc-faint)]">
                      {day.date.slice(5)}
                    </span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--hc-canvas)]">
                      <div
                        className="h-full rounded-full bg-[var(--hc-accent)]/85"
                        style={{ width: `${(day.volume_m3 / max) * 100}%` }}
                      />
                    </div>
                    <span className="hc-num w-20 shrink-0 text-right text-[10.5px] text-[var(--hc-ink)]">
                      {fmtNumber(day.volume_m3, 1)} m³
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <Empty icon="history" title="暂无数据" hint="保存田块并录入作物后即可解算。" />
          )}
        </section>

        {/* per-field assumptions */}
        {summary?.fields.length ? (
          <section className="mt-3 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
            <SectionTitle>各田块汇总</SectionTitle>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-[11px]">
                <thead className="text-[var(--hc-faint)]">
                  <tr>
                    <th className="py-1.5 text-left font-medium">田块</th>
                    <th className="py-1.5 text-right font-medium">面积</th>
                    <th className="py-1.5 text-right font-medium">作物</th>
                    <th className="py-1.5 text-right font-medium">Kc</th>
                    <th className="py-1.5 text-right font-medium">净需水</th>
                    <th className="py-1.5 text-right font-medium">15 天水量</th>
                  </tr>
                </thead>
                <tbody className="hc-num">
                  {summary.fields.map((entry) => (
                    <tr key={entry.field.id} className="border-t border-[var(--hc-line)]">
                      <td className="py-1.5 text-left text-[var(--hc-ink)]">{entry.field.name}</td>
                      <td className="py-1.5 text-right text-[var(--hc-muted)]">
                        {fmtNumber(entry.area.mu, 2)} 亩
                      </td>
                      <td className="py-1.5 text-right text-[var(--hc-muted)]">
                        {entry.crop.label} · {entry.crop.stage_label}
                      </td>
                      <td className="py-1.5 text-right text-[var(--hc-muted)]">{entry.crop.kc.toFixed(2)}</td>
                      <td className="py-1.5 text-right text-[var(--hc-muted)]">
                        {fmtMm(entry.totals.net_mm)}
                      </td>
                      <td className="py-1.5 text-right text-[var(--hc-accent)]">
                        {fmtM3(entry.totals.volume_m3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {/* query log */}
        <section className="mt-3 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle right={loading ? <Spinner size={12} /> : null}>解算记录</SectionTitle>
          {logs.length === 0 && !loading ? (
            <Empty icon="history" title="还没有解算记录" hint="打开田块详情查看需水量后会自动留痕。" />
          ) : (
            <ul className="flex flex-col">
              {logs.map((log) => (
                <li
                  key={log.id}
                  className="flex items-center gap-2 border-b border-[var(--hc-line)] py-2 last:border-0"
                >
                  <Icon name="water" size={13} className="shrink-0 text-[var(--hc-sky)]" />
                  <span className="truncate text-[11.5px] text-[var(--hc-ink)]">{log.field_name}</span>
                  <span className="hc-chip shrink-0">{log.days} 天</span>
                  <span className="hc-num ml-auto shrink-0 text-[11px] text-[var(--hc-accent)]">
                    {log.totals.volume_m3 ? fmtM3(log.totals.volume_m3) : '—'}
                  </span>
                  <span className="w-16 shrink-0 text-right text-[10px] text-[var(--hc-faint)]">
                    {relativeTime(log.computed_at)}
                  </span>
                  <span className="hidden w-24 shrink-0 text-right text-[10px] text-[var(--hc-faint)] sm:block">
                    {fmtDateTime(log.computed_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="h-6" />
      </div>
    </div>
  )
}
