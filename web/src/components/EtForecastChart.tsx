import { useId, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { EtForecastPeriod } from '../types'
import { fmtM3, fmtMm, fmtNumber } from '../lib/format'

export type EtRangeKey = 'day' | 'week' | 'month'

export interface EtRangePoint {
  key: EtRangeKey
  label: string
  period: EtForecastPeriod
}

interface Props {
  points: EtRangePoint[]
  selected: EtRangeKey
  onSelect: (key: EtRangeKey) => void
}

type Metric = 'et' | 'water'

interface SeriesSpec {
  key: string
  label: string
  color: string
  values: Array<number | null>
}

interface Coord {
  x: number
  y: number
  value: number
}

interface SeriesView extends SeriesSpec {
  coords: Array<Coord | null>
  segments: Coord[][]
}

const WIDTH = 280
const HEIGHT = 124
const PAD = { top: 16, right: 8, bottom: 8, left: 38 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom
const BASELINE = PAD.top + PLOT_H

const METRICS: Array<{ key: Metric; label: string; unit: string }> = [
  { key: 'et', label: '蒸散发(mm)', unit: 'mm' },
  { key: 'water', label: '补水量(m³)', unit: 'm³' },
]

function isFiniteNumber(value: number | null): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function niceStep(rough: number): number {
  const exponent = Math.floor(Math.log10(rough))
  const base = 10 ** exponent
  const normalized = rough / base
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10
  return step * base
}

function buildScale(maxValue: number): { top: number; ticks: number[]; step: number } {
  if (!(maxValue > 0)) return { top: 1, ticks: [0, 0.5, 1], step: 0.5 }
  const step = niceStep(maxValue / 4)
  const top = Math.ceil(maxValue / step) * step
  const ticks: number[] = []
  for (let value = 0; value <= top + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)))
  }
  return { top, ticks, step }
}

function formatTick(value: number, step: number): string {
  if (value === 0) return '0'
  if (Math.abs(value) >= 1000) {
    return `${fmtNumber(value / 1000, value % 1000 === 0 ? 0 : 1)}k`
  }
  const digits = step >= 1 ? (Number.isInteger(step) ? 0 : 1) : step >= 0.1 ? (Number.isInteger(step * 10) ? 1 : 2) : 3
  return fmtNumber(value, digits)
}

function linePath(points: Coord[]): string {
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(' ')
}

function areaPath(points: Coord[], baseline: number): string {
  if (points.length < 2) return ''
  const first = points[0]
  const last = points[points.length - 1]
  return `${linePath(points)} L${last.x.toFixed(2)},${baseline} L${first.x.toFixed(2)},${baseline} Z`
}

/**
 * Compares the three existing forecast horizons on one categorical axis.
 * The API only returns three cumulative points, so this deliberately draws
 * no interpolated daily series. Null values break the line instead of bridging.
 */
export default function EtForecastChart({ points, selected, onSelect }: Props) {
  const [metric, setMetric] = useState<Metric>('et')
  const [hovered, setHovered] = useState<number | null>(null)
  const gradientPrefix = useId().replace(/[^a-zA-Z0-9_-]/g, '')

  const metricSpec = METRICS.find((item) => item.key === metric) ?? METRICS[0]

  const series = useMemo<SeriesSpec[]>(() => {
    if (metric === 'et') {
      return [
        {
          key: 'et',
          label: '蒸散发',
          color: 'var(--hc-amber)',
          values: points.map((point) => point.period.et_mm),
        },
      ]
    }
    return [
      {
        key: 'net',
        label: '净补水',
        color: 'var(--hc-sky)',
        values: points.map((point) => point.period.net_volume_m3),
      },
      {
        key: 'gross',
        label: '毛供水',
        color: 'var(--hc-accent)',
        values: points.map((point) => point.period.gross_volume_m3),
      },
    ]
  }, [metric, points])

  const chart = useMemo(() => {
    const count = Math.max(1, points.length)
    const finiteValues = series.flatMap((item) => item.values.filter(isFiniteNumber))
    const maxValue = finiteValues.length ? Math.max(...finiteValues) : 0
    const scale = buildScale(maxValue)
    const xAt = (index: number) => PAD.left + (PLOT_W * (index + 0.5)) / count
    const yAt = (value: number) => PAD.top + PLOT_H - (Math.max(0, value) / scale.top) * PLOT_H

    const rendered: SeriesView[] = series.map((item) => {
      const coords = item.values.map((value, index) =>
        isFiniteNumber(value) ? { x: xAt(index), y: yAt(value), value } : null,
      )
      const segments: Coord[][] = []
      let run: Coord[] = []
      for (const coord of coords) {
        if (coord) {
          run.push(coord)
        } else if (run.length) {
          segments.push(run)
          run = []
        }
      }
      if (run.length) segments.push(run)
      return { ...item, coords, segments }
    })

    return { scale, xAt, yAt, rendered, count }
  }, [series, points.length])

  const selectedIndex = Math.max(0, points.findIndex((point) => point.key === selected))
  const activeIndex = hovered ?? selectedIndex
  const activePoint = points[activeIndex]
  const hasData = chart.rendered.some((item) => item.coords.some((coord) => coord !== null))
  const bandWidth = PLOT_W / chart.count

  const readout = activePoint
    ? metric === 'et'
      ? fmtMm(activePoint.period.et_mm)
      : `净 ${fmtM3(activePoint.period.net_volume_m3)} · 毛 ${fmtM3(activePoint.period.gross_volume_m3)}`
    : '—'

  const ariaSummary = points
    .map((point) =>
      metric === 'et'
        ? `${point.label} ${fmtMm(point.period.et_mm)}`
        : `${point.label} 净补水 ${fmtM3(point.period.net_volume_m3)}，毛供水 ${fmtM3(point.period.gross_volume_m3)}`,
    )
    .join('；')

  function indexAt(event: ReactPointerEvent<SVGSVGElement>): number | null {
    if (!points.length) return null
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.width) return null
    const viewX = ((event.clientX - rect.left) / rect.width) * WIDTH
    const ratio = (viewX - PAD.left) / PLOT_W
    const index = Math.floor(ratio * points.length)
    return Math.min(points.length - 1, Math.max(0, index))
  }

  if (!points.length) {
    return (
      <div className="rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface)] px-2 py-6 text-center text-[10px] text-[var(--hc-faint)]">
        暂无可对比的预测范围
      </div>
    )
  }

  return (
    <div className="min-w-0 rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface)] p-2">
      <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-1.5">
            <h4 className="text-[11px] font-medium leading-tight text-[var(--hc-ink)]">预测范围对比</h4>
            <span className="text-[8.5px] text-[var(--hc-faint)]">各范围累计量</span>
          </div>
          <p className="mt-0.5 text-[8.5px] leading-tight text-[var(--hc-faint)]">
            当天与未来 7 / 30 天累计对比
          </p>
        </div>
        <div
          role="group"
          aria-label="图表指标"
          className="flex shrink-0 items-center rounded-md border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-0.5"
        >
          {METRICS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={metric === item.key}
              onClick={() => {
                setMetric(item.key)
                setHovered(null)
              }}
              className={`rounded-[5px] px-1.5 py-1 text-[9px] transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--hc-accent)] ${
                metric === item.key
                  ? 'bg-[var(--hc-surface)] text-[var(--hc-ink)] shadow-sm'
                  : 'text-[var(--hc-faint)] hover:text-[var(--hc-muted)]'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {hasData ? (
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="mt-1 block h-auto w-full touch-pan-y"
          style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}
          role="img"
          aria-label={`预测范围对比，${metricSpec.unit}：${ariaSummary}`}
          onPointerDown={(event) => {
            const index = indexAt(event)
            if (index === null) return
            setHovered(index)
            onSelect(points[index].key)
          }}
          onPointerMove={(event) => {
            const index = indexAt(event)
            if (index !== null) setHovered(index)
          }}
          onPointerLeave={() => setHovered(null)}
          onPointerCancel={() => setHovered(null)}
        >
          <defs>
            {chart.rendered.map((item, index) => (
              <linearGradient
                key={item.key}
                id={`etchart-${gradientPrefix}-${index}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={item.color} stopOpacity={metric === 'et' ? 0.26 : 0.16} />
                <stop offset="100%" stopColor={item.color} stopOpacity="0.01" />
              </linearGradient>
            ))}
          </defs>

          <rect
            x={chart.xAt(selectedIndex) - bandWidth / 2}
            y={PAD.top}
            width={bandWidth}
            height={PLOT_H}
            fill="var(--hc-accent)"
            opacity="0.05"
          />

          {chart.scale.ticks.map((tick) => {
            const y = chart.yAt(tick)
            return (
              <g key={tick}>
                <line
                  x1={PAD.left}
                  x2={WIDTH - PAD.right}
                  y1={y}
                  y2={y}
                  stroke="var(--hc-line)"
                  strokeWidth="0.7"
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={PAD.left - 4}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize="8"
                  fill="var(--hc-faint)"
                  className="hc-num"
                >
                  {formatTick(tick, chart.scale.step)}
                </text>
              </g>
            )
          })}

          <text x={PAD.left} y={PAD.top - 6} fontSize="8" fill="var(--hc-faint)">
            {metricSpec.unit}
          </text>

          <line
            x1={chart.xAt(selectedIndex)}
            x2={chart.xAt(selectedIndex)}
            y1={PAD.top}
            y2={BASELINE}
            stroke="var(--hc-ink)"
            strokeOpacity="0.2"
            strokeWidth="1"
            strokeDasharray="2 3"
            vectorEffect="non-scaling-stroke"
          />

          {points.map((point, index) => (
            <line
              key={`tick-${point.key}`}
              x1={chart.xAt(index)}
              x2={chart.xAt(index)}
              y1={BASELINE}
              y2={BASELINE + 3}
              stroke={index === selectedIndex ? 'var(--hc-accent)' : 'var(--hc-line)'}
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {chart.rendered.map((item, seriesIndex) => (
            <g key={`area-layer-${item.key}`}>
              {item.segments.map((segment, segmentIndex) =>
                segment.length > 1 ? (
                  <path
                    key={`area-${segmentIndex}`}
                    d={areaPath(segment, BASELINE)}
                    fill={`url(#etchart-${gradientPrefix}-${seriesIndex})`}
                  />
                ) : null,
              )}
            </g>
          ))}

          {chart.rendered.map((item) => (
            <g key={`line-layer-${item.key}`}>
              {item.segments.map((segment, segmentIndex) =>
                segment.length > 1 ? (
                  <path
                    key={`line-${segmentIndex}`}
                    d={linePath(segment)}
                    fill="none"
                    stroke={item.color}
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                ) : null,
              )}
            </g>
          ))}

          {chart.rendered.map((item) => (
            <g key={`point-layer-${item.key}`}>
              {item.coords.map((coord, index) =>
                coord ? (
                  <g key={`point-${item.key}-${index}`}>
                    {index === selectedIndex && (
                      <circle
                        cx={coord.x}
                        cy={coord.y}
                        r="4.6"
                        fill="none"
                        stroke={item.color}
                        strokeOpacity="0.45"
                        strokeWidth="1.2"
                        vectorEffect="non-scaling-stroke"
                      />
                    )}
                    <circle
                      cx={coord.x}
                      cy={coord.y}
                      r={index === selectedIndex ? 2.8 : 2.1}
                      fill={item.color}
                      stroke="var(--hc-surface)"
                      strokeWidth="1"
                      vectorEffect="non-scaling-stroke"
                    />
                  </g>
                ) : null,
              )}
            </g>
          ))}

          <line
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={BASELINE}
            y2={BASELINE}
            stroke="var(--hc-line)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      ) : (
        <div className="flex h-[96px] items-center justify-center text-[10px] text-[var(--hc-faint)]">
          该指标暂无可绘制的数值
        </div>
      )}

      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-[9px]">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {chart.rendered.map((item) => (
            <span key={item.key} className="inline-flex items-center gap-1 text-[var(--hc-muted)]">
              <span
                className="inline-block h-[3px] w-3 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              {item.label} {metric === 'et' ? 'mm' : 'm³'}
            </span>
          ))}
        </div>
        <span className="text-[var(--hc-faint)]">
          {activePoint?.label} · <span className="hc-num text-[var(--hc-muted)]">{readout}</span>
        </span>
      </div>

      <div className="mt-1.5 grid grid-cols-3 gap-1" role="group" aria-label="选择预测范围">
        {points.map((point, index) => (
          <button
            key={point.key}
            type="button"
            aria-pressed={index === selectedIndex}
            onClick={() => {
              setHovered(index)
              onSelect(point.key)
            }}
            onMouseEnter={() => setHovered(index)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(index)}
            onBlur={() => setHovered(null)}
            className={`rounded-md border px-1 py-1 text-[9.5px] transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--hc-accent)] ${
              index === selectedIndex
                ? 'border-[var(--hc-accent)]/55 bg-[var(--hc-accent)]/12 text-[var(--hc-accent)]'
                : 'border-[var(--hc-line)] text-[var(--hc-faint)] hover:text-[var(--hc-muted)]'
            }`}
          >
            {point.label}
          </button>
        ))}
      </div>
    </div>
  )
}
