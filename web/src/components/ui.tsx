import type { ReactNode } from 'react'
import { useUI } from '../store/ui'

const PATHS: Record<string, string> = {
  map: 'M9 4.5 3.5 6.8v13.2L9 17.7l6 2.3 5.5-2.3V4.5L15 6.8 9 4.5Z M9 4.5v13.2 M15 6.8V20',
  fields: 'M3.5 7.5h17v11h-17z M3.5 12h17 M9 7.5v11 M15 7.5v11',
  water: 'M12 3.2c3.4 4 5.2 6.6 5.2 9a5.2 5.2 0 0 1-10.4 0c0-2.4 1.8-5 5.2-9Z',
  history: 'M3.6 12a8.4 8.4 0 1 0 2.6-6.1 M3.6 4.6V9h4.4 M12 7.6V12l3.2 2',
  settings:
    'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z M19.4 13.6a7.6 7.6 0 0 0 0-3.2l2-1.2-2-3.4-2 1a7.6 7.6 0 0 0-2.8-1.6L14.2 2h-4.4l-.4 2.2A7.6 7.6 0 0 0 6.6 5.8l-2-1-2 3.4 2 1.2a7.6 7.6 0 0 0 0 3.2l-2 1.2 2 3.4 2-1a7.6 7.6 0 0 0 2.8 1.6l.4 2.2h4.4l.4-2.2a7.6 7.6 0 0 0 2.8-1.6l2 1 2-3.4-2-1.2Z',
  users: 'M8.5 11a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z M2.8 20c0-3.1 2.6-5.6 5.7-5.6s5.7 2.5 5.7 5.6 M16 5.2a3 3 0 0 1 0 5.9 M17.5 14.8c2.2.6 3.7 2.6 3.7 5.2',
  layers: 'M12 3.2 3 8l9 4.8L21 8l-9-4.8Z M3 12.4l9 4.8 9-4.8 M3 16.8l9 4.8 9-4.8',
  draw: 'M4 20l1-4.4 9.6-9.6 3.4 3.4L8.4 19 4 20Z M13.6 5l3.4 3.4',
  locate: 'M12 3v2.4 M12 18.6V21 M3 12h2.4 M18.6 12H21 M12 16.4a4.4 4.4 0 1 0 0-8.8 4.4 4.4 0 0 0 0 8.8Z',
  scan: 'M4 8V5.6A1.6 1.6 0 0 1 5.6 4H8 M16 4h2.4A1.6 1.6 0 0 1 20 5.6V8 M20 16v2.4a1.6 1.6 0 0 1-1.6 1.6H16 M8 20H5.6A1.6 1.6 0 0 1 4 18.4V16 M4 12h16',
  pencil: 'M4 20h4l10.5-10.5-4-4L4 16v4Z M13.5 5.5l4 4',
  trash: 'M4.5 7h15 M9.5 7V4.6h5V7 M6.4 7l.9 12.4h9.4L17.6 7 M10 11v5 M14 11v5',
  close: 'M6 6l12 12 M18 6 6 18',
  chevron: 'M8 10l4 4 4-4',
  plus: 'M12 5v14 M5 12h14',
  sun: 'M12 4.4V2.6 M12 21.4v-1.8 M4.4 12H2.6 M21.4 12h-1.8 M6.6 6.6 5.3 5.3 M18.7 18.7l-1.3-1.3 M17.4 6.6l1.3-1.3 M5.3 18.7l1.3-1.3 M12 16.6a4.6 4.6 0 1 0 0-9.2 4.6 4.6 0 0 0 0 9.2Z',
  moon: 'M20 14.4A8.4 8.4 0 0 1 9.6 4a8.6 8.6 0 1 0 10.4 10.4Z',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.7 M20 3.6V9h-5.4',
  logout: 'M15 8.4V5.6A1.6 1.6 0 0 0 13.4 4H5.6A1.6 1.6 0 0 0 4 5.6v12.8A1.6 1.6 0 0 0 5.6 20h7.8a1.6 1.6 0 0 0 1.6-1.6v-2.8 M9.5 12h11 M17.5 9l3 3-3 3',
  check: 'M5 12.5 9.5 17 19 7.5',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 11v5 M12 8h.01',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Z M12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  menu: 'M4 7h16 M4 12h16 M4 17h16',
  crop: 'M12 21V9 M12 9c0-3.3 2.2-5.5 5.5-5.5C17.5 6.8 15.3 9 12 9Z M12 13c0-3.3-2.2-5.5-5.5-5.5C6.5 10.8 8.7 13 12 13Z',
}

export function Icon({
  name,
  size = 18,
  className = '',
  strokeWidth = 1.7,
}: {
  name: keyof typeof PATHS | string
  size?: number
  className?: string
  strokeWidth?: number
}) {
  const path = PATHS[name] ?? PATHS.info
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {path.split(' M').map((segment, index) => (
        <path key={index} d={index === 0 ? segment : `M${segment}`} />
      ))}
    </svg>
  )
}

export function Stat({
  label,
  value,
  unit,
  hint,
  accent = false,
  size = 'md',
}: {
  label: string
  value: ReactNode
  unit?: string
  hint?: string
  accent?: boolean
  size?: 'sm' | 'md' | 'lg'
}) {
  const valueSize = size === 'lg' ? 'text-2xl' : size === 'sm' ? 'text-sm' : 'text-lg'
  return (
    <div className="flex flex-col gap-0.5">
      <span className="hc-label">{label}</span>
      <span
        className={`hc-num ${valueSize} font-semibold leading-tight ${
          accent ? 'text-[var(--hc-accent)]' : 'text-[var(--hc-ink)]'
        }`}
      >
        {value}
        {unit && <span className="ml-1 text-[11px] font-normal text-[var(--hc-faint)]">{unit}</span>}
      </span>
      {hint && <span className="text-[10px] text-[var(--hc-faint)]">{hint}</span>}
    </div>
  )
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <span className="hc-label">{children}</span>
      {right}
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-[var(--hc-line-strong,#2a3a49)] border-t-[var(--hc-accent)]"
      style={{ width: size, height: size }}
    />
  )
}

export function Toast() {
  const toast = useUI((state) => state.toast)
  if (!toast) return null
  const tone =
    toast.tone === 'error'
      ? 'border-[var(--hc-danger)] text-[var(--hc-danger)]'
      : toast.tone === 'success'
        ? 'border-[var(--hc-accent)] text-[var(--hc-accent)]'
        : 'border-[var(--hc-line)] text-[var(--hc-ink)]'
  return (
    <div className="pointer-events-none fixed inset-x-0 top-[max(env(safe-area-inset-top),12px)] z-[80] flex justify-center px-4">
      <div
        className={`hc-rise max-w-md rounded-xl border bg-[var(--hc-surface)] px-3.5 py-2.5 text-[12.5px] shadow-2xl ${tone}`}
      >
        {toast.text}
      </div>
    </div>
  )
}

export function Empty({ icon = 'info', title, hint }: { icon?: string; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <Icon name={icon} size={26} className="text-[var(--hc-faint)]" />
      <div className="text-[13px] text-[var(--hc-muted)]">{title}</div>
      {hint && <div className="max-w-[240px] text-[11px] leading-relaxed text-[var(--hc-faint)]">{hint}</div>}
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="flex rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`flex-1 rounded-[7px] px-2 py-1.5 text-[11.5px] font-medium transition ${
            value === option.value
              ? 'bg-[var(--hc-surface)] text-[var(--hc-ink)] shadow-sm'
              : 'text-[var(--hc-faint)] hover:text-[var(--hc-muted)]'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
