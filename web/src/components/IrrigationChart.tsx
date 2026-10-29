import { useMemo, useState } from 'react'
import type { IrrigationDay } from '../types'
import { fmtDate, fmtM3, fmtWeekday } from '../lib/format'

interface Props {
  series: IrrigationDay[]
  height?: number
  compact?: boolean
}

/** Daily water demand as a banded area chart (5-year min/max envelope + mean). */
export default function IrrigationChart({ series, height = 132, compact = false }: Props) {
  const [active, setActive] = useState<number | null>(null)

  const view = useMemo(() => {
    if (!series.length) return null
    const values = series.map((day) => day.volume_m3)
    // Scale the volume by the ET envelope so the band reflects climate spread.
    const upper = series.map((day) => {
      const ref = day.et0_mm || 1e-6
      return day.et0_max ? (day.et0_max / ref) * day.volume_m3 : day.volume_m3
    })
    const lower = series.map((day) => {
      const ref = day.et0_mm || 1e-6
      return day.et0_min ? (day.et0_min / ref) * day.volume_m3 : day.volume_m3
    })
    const max = Math.max(...values, ...upper) * 1.12 || 1
    const min = Math.min(0, ...lower)
    const width = 100
    const step = series.length > 1 ? width / (series.length - 1) : width

    const toPoint = (value: number, index: number) => {
      const x = series.length > 1 ? index * step : width / 2
      const y = height - ((value - min) / (max - min || 1)) * height
      return [x, y] as const
    }

    const line = values.map((value, index) => toPoint(value, index))
    const path = line.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
    const area = `${path} L${line[line.length - 1][0].toFixed(2)},${height} L${line[0][0].toFixed(2)},${height} Z`
    const bandTop = upper.map((value, index) => toPoint(value, index))
    const bandBottom = lower.map((value, index) => toPoint(value, index)).reverse()
    const band = `M${bandTop.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L')} L${bandBottom
      .map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`)
      .join(' L')} Z`

    return { path, area, band, line, max, min, step, values }
  }, [series, height])

  if (!view) return null
  const activeDay = active !== null ? series[active] : null

  return (
    <div className="w-full">
      <div className="relative w-full" style={{ height }}>
        <svg
          viewBox={`0 0 100 ${height}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          onMouseLeave={() => setActive(null)}
          onMouseMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect()
            const ratio = (event.clientX - rect.left) / rect.width
            const index = Math.round(ratio * (series.length - 1))
            setActive(Math.max(0, Math.min(series.length - 1, index)))
          }}
          onTouchStart={(event) => {
            const rect = event.currentTarget.getBoundingClientRect()
            const ratio = (event.touches[0].clientX - rect.left) / rect.width
            const index = Math.round(ratio * (series.length - 1))
            setActive(Math.max(0, Math.min(series.length - 1, index)))
          }}
          onTouchMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect()
            const ratio = (event.touches[0].clientX - rect.left) / rect.width
            const index = Math.round(ratio * (series.length - 1))
            setActive(Math.max(0, Math.min(series.length - 1, index)))
          }}
        >
          <defs>
            <linearGradient id="hcArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--hc-accent)" stopOpacity="0.34" />
              <stop offset="100%" stopColor="var(--hc-accent)" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path d={view.band} fill="var(--hc-sky)" opacity="0.1" />
          <path d={view.area} fill="url(#hcArea)" />
          <path
            d={view.path}
            fill="none"
            stroke="var(--hc-accent)"
            strokeWidth={1.4}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
          />
          {active !== null && (
            <line
              x1={view.line[active][0]}
              x2={view.line[active][0]}
              y1={0}
              y2={height}
              stroke="var(--hc-sky)"
              strokeWidth={1}
              strokeDasharray="2 2"
              vectorEffect="non-scaling-stroke"
            />
          )}
          {active !== null && (
            <circle
              cx={view.line[active][0]}
              cy={view.line[active][1]}
              r={2.4}
              fill="var(--hc-sky)"
              stroke="var(--hc-surface)"
              strokeWidth={1.2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>

      <div className="mt-1.5 flex items-baseline justify-between gap-2">
        {compact ? (
          <span className="text-[10px] text-[var(--hc-faint)]">
            {fmtDate(series[0].date)} — {fmtDate(series[series.length - 1].date)}
          </span>
        ) : (
          series.map((day, index) => (
            <button
              key={day.date}
              type="button"
              onMouseEnter={() => setActive(index)}
              className={`flex flex-col items-center gap-0.5 rounded-md px-0.5 py-0.5 text-[9.5px] transition ${
                active === index ? 'text-[var(--hc-ink)]' : 'text-[var(--hc-faint)]'
              }`}
            >
              <span>{fmtWeekday(day.date).replace('周', '')}</span>
              <span className="hc-num">{Math.round(day.volume_m3)}</span>
            </button>
          ))
        )}
        {activeDay && (
          <span className="ml-auto whitespace-nowrap text-[10.5px] text-[var(--hc-muted)]">
            {fmtDate(activeDay.date)} · {fmtM3(activeDay.volume_m3)} ·{' '}
            <span className="text-[var(--hc-accent)]">{activeDay.gross_mm.toFixed(2)} mm</span>
          </span>
        )}
      </div>
    </div>
  )
}
