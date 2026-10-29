import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Icon, Spinner } from './ui'
import type { RegionHit } from '../types'

const LEVEL_LABEL: Record<string, string> = {
  province: '省',
  city: '市',
  district: '区县',
  town: '乡镇',
  village: '村',
}

interface Props {
  onPick: (hit: RegionHit) => void
  placeholder?: string
  className?: string
  autoFocus?: boolean
  label?: string
}

/**
 * Fuzzy picker over the bundled 行政区划 index (3400 entries: 省/市/区县).
 * Matches names, full names and adcodes, so "3705", "东营" and "山东东营" all hit.
 */
export default function RegionPicker({
  onPick,
  placeholder = '搜索省/市/区县，或直接输入行政区代码',
  className = '',
  autoFocus = false,
  label,
}: Props) {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<RegionHit[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    const text = query.trim()
    if (!text) {
      setHits([])
      setOpen(false)
      setError(null)
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const payload = await api.geoSearch(text, 8)
        if (cancelled) return
        setHits(payload.results)
        setActive(0)
        setOpen(true)
        setError(payload.count === 0 ? '没有匹配的行政区' : null)
      } catch (err) {
        if (!cancelled) {
          setHits([])
          setError((err as Error).message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 170)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  function choose(hit: RegionHit) {
    onPick(hit)
    setQuery(hit.fullname)
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActive((index) => Math.min(index + 1, Math.max(hits.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      if (open && hits[active]) {
        event.preventDefault()
        choose(hits[active])
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={boxRef} className={`relative ${className}`}>
      {label && <div className="hc-label mb-1">{label}</div>}
      <div className="relative">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => hits.length && setOpen(true)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="hc-input h-9 pl-8 text-[12.5px]"
          spellCheck={false}
        />
        <Icon
          name="target"
          size={14}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--hc-faint)]"
        />
        {loading && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2">
            <Spinner size={13} />
          </span>
        )}
        {!loading && query && (
          <button
            type="button"
            onClick={() => {
              setQuery('')
              setHits([])
              setOpen(false)
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--hc-faint)] hover:text-[var(--hc-ink)]"
            aria-label="清空"
          >
            <Icon name="close" size={12} />
          </button>
        )}
      </div>

      {open && hits.length > 0 && (
        <ul className="absolute left-0 right-0 top-11 z-50 max-h-[320px] overflow-y-auto rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface)] py-1 shadow-2xl">
          {hits.map((hit, index) => (
            <li key={hit.adcode}>
              <button
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(hit)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left ${
                  index === active ? 'bg-[var(--hc-surface-2)]' : ''
                }`}
              >
                <Icon name="target" size={12} className="shrink-0 text-[var(--hc-sky)]" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] text-[var(--hc-ink)]">
                    {hit.fullname}
                  </span>
                  <span className="hc-num block text-[10px] text-[var(--hc-faint)]">
                    {hit.adcode}
                    {hit.lon && hit.lat ? ` · ${hit.lon.toFixed(3)}, ${hit.lat.toFixed(3)}` : ''}
                    {hit.precision === 'district-center' ? ' · 按所属区县近似定位' : ''}
                  </span>
                </span>
                <span className="hc-chip shrink-0">{LEVEL_LABEL[hit.level] ?? hit.level}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && hits.length === 0 && error && (
        <div className="absolute left-0 right-0 top-11 z-50 rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface)] px-3 py-2 text-[11px] text-[var(--hc-faint)] shadow-2xl">
          {error}
        </div>
      )}
    </div>
  )
}
