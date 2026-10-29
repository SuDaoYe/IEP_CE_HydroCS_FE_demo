import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { warmView } from '../lib/actions'
import { flyToPoint } from './mapBridge'
import RegionPicker from './RegionPicker'
import { useAuth } from '../store/auth'
import { useData } from '../store/data'
import { useUI } from '../store/ui'
import { Icon, Spinner } from './ui'
import type { RegionHit } from '../types'

interface Props {
  title?: string
  subtitle?: string
}

const ZOOM_BY_LEVEL: Record<string, number> = {
  province: 8,
  city: 11,
  district: 13,
  town: 14,
  village: 15,
}

export default function TopBar({ title = 'HYDRO·CS', subtitle }: Props) {
  const user = useAuth((state) => state.user)
  const logout = useAuth((state) => state.logout)
  const theme = useUI((state) => state.theme)
  const toggleTheme = useUI((state) => state.toggleTheme)
  const offline = useData((state) => state.offline)
  const pendingCount = useData((state) => state.pendingCount)
  const busy = useUI((state) => state.busyLabel)
  const notify = useUI((state) => state.notify)

  const [picked, setPicked] = useState<RegionHit | null>(null)
  const [providerCount, setProviderCount] = useState<number | null>(null)
  const probed = useRef(false)

  // A single cheap call doubles as a reachability probe for the header chip.
  useEffect(() => {
    if (probed.current) return
    probed.current = true
    api
      .providers()
      .then((providers) => setProviderCount(providers.filter((item) => item.enabled).length))
      .catch(() => setProviderCount(null))
  }, [])

  function handlePick(hit: RegionHit) {
    setPicked(hit)
    if (hit.lon !== null && hit.lat !== null) {
      const zoom = ZOOM_BY_LEVEL[hit.level] ?? 12
      warmView(hit.lon, hit.lat, zoom)
      flyToPoint(hit.lon, hit.lat, zoom)
      notify(
        hit.precision === 'district-center'
          ? `已定位到 ${hit.fullname} 所属区县中心，村镇级没有内置边界，请在地图上微调`
          : `已定位到 ${hit.fullname}`,
      )
    } else {
      notify(`${hit.fullname} 没有中心坐标，可在管理端按行政区统计`, 'error')
    }
  }

  return (
    <header className="relative z-30 flex h-14 shrink-0 items-center gap-3 border-b border-[var(--hc-line)] bg-[var(--hc-surface)] px-3 sm:px-4">
      <div className="flex items-center gap-2.5">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--hc-accent)]/14 text-[var(--hc-accent)]">
          <Icon name="water" size={16} />
        </div>
        <div className="leading-none">
          <div className="text-[13px] font-semibold tracking-[0.14em] text-[var(--hc-ink)]">{title}</div>
          <div className="mt-1 hidden text-[10px] text-[var(--hc-faint)] sm:block">
            {subtitle ?? '卫星影像 · 田块识别 · 灌溉需水'}
          </div>
        </div>
      </div>

      <div className="ml-auto flex max-w-[460px] flex-1 items-center gap-2">
        <RegionPicker onPick={handlePick} className="w-full" />
      </div>

      <div className="flex items-center gap-1.5">
        {busy && (
          <span className="hidden items-center gap-1.5 rounded-full border border-[var(--hc-line)] px-2.5 py-1 text-[10.5px] text-[var(--hc-muted)] sm:flex">
            <Spinner size={11} />
            {busy}
          </span>
        )}
        {picked && (
          <span className="hc-chip hidden max-w-[170px] truncate lg:inline-flex">{picked.fullname}</span>
        )}
        {offline && (
          <span className="hc-chip border-[var(--hc-amber)]/50 text-[var(--hc-amber)]">
            离线{pendingCount ? ` · ${pendingCount} 待同步` : ''}
          </span>
        )}
        {providerCount !== null && (
          <span className="hc-chip hidden xl:inline-flex">影像源 {providerCount}</span>
        )}
        <button
          type="button"
          onClick={toggleTheme}
          className="hc-btn h-9 w-9 !min-h-0 !px-0"
          aria-label="切换主题"
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15} />
        </button>
        <div className="hidden items-center gap-2 pl-1 sm:flex">
          <div className="text-right leading-tight">
            <div className="text-[12px] text-[var(--hc-ink)]">{user?.name}</div>
            <div className="text-[10px] text-[var(--hc-faint)]">
              {user?.role === 'admin' ? '管理员' : '农户'}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={logout}
          className="hc-btn h-9 w-9 !min-h-0 !px-0 text-[var(--hc-muted)]"
          aria-label="退出登录"
        >
          <Icon name="logout" size={15} />
        </button>
      </div>
    </header>
  )
}
