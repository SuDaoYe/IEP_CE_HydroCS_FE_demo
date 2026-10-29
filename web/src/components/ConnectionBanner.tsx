import { useEffect, useState } from 'react'
import { onConnectionChange } from '../lib/api'
import { useAuth } from '../store/auth'
import { useData } from '../store/data'
import { Icon, Spinner } from './ui'

/**
 * Persistent banner instead of a transient toast: if the API host is
 * unreachable the user needs a visible retry affordance, not a message that
 * disappears after three seconds.
 */
export default function ConnectionBanner() {
  const [offline, setOffline] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => onConnectionChange((down) => {
    setOffline(down)
    if (down) setDismissed(false)
  }), [])

  // While down, probe again every 20 s so the banner clears itself.
  useEffect(() => {
    if (!offline) return
    const timer = window.setInterval(() => void retry(true), 20000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offline])

  async function retry(silent = false) {
    if (retrying) return
    setRetrying(true)
    try {
      await useAuth.getState().refresh()
      await useData.getState().load()
      setOffline(false)
    } catch {
      if (!silent) setOffline(true)
    } finally {
      setRetrying(false)
    }
  }

  if (!offline || dismissed) return null

  return (
    <div className="fixed inset-x-0 top-0 z-[70] flex justify-center px-3 pt-2">
      <div className="hc-rise flex w-full max-w-[560px] items-center gap-2.5 rounded-xl border border-[var(--hc-danger)]/50 bg-[var(--hc-surface)] px-3 py-2 shadow-2xl">
        <Icon name="info" size={15} className="shrink-0 text-[var(--hc-danger)]" />
        <div className="min-w-0 flex-1 text-[11.5px] leading-snug text-[var(--hc-muted)]">
          <span className="text-[var(--hc-ink)]">连不上后端服务。</span>{' '}
          请确认在同一台电脑上启动了服务，并直接访问
          <span className="hc-num text-[var(--hc-ink)]"> http://127.0.0.1:8000 </span>
          （不要用 vite 预览端口或双击 index.html 打开）。
        </div>
        <button
          type="button"
          onClick={() => void retry()}
          className="hc-btn h-8 shrink-0 px-2 text-[11px]"
          disabled={retrying}
        >
          {retrying ? <Spinner size={12} /> : <Icon name="refresh" size={12} />}
          重试
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 text-[var(--hc-faint)] hover:text-[var(--hc-ink)]"
          aria-label="关闭提示"
        >
          <Icon name="close" size={13} />
        </button>
      </div>
    </div>
  )
}
