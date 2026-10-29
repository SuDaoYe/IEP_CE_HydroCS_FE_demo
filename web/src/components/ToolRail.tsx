import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { useData } from '../store/data'
import { useUI } from '../store/ui'
import { useWork } from '../store/work'
import { cycleProvider, editGeometry, locateMe, recognizeCurrentView } from '../lib/actions'
import { Icon } from './ui'

interface RailButtonProps {
  icon: string
  label: string
  onClick: () => void
  active?: boolean
  primary?: boolean
  badge?: number
}

function RailButton({ icon, label, onClick, active, primary, badge }: RailButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`relative flex h-11 w-11 flex-col items-center justify-center gap-0.5 rounded-xl border text-[9px] transition ${
        primary
          ? 'border-transparent bg-[var(--hc-accent)] text-[#05231a]'
          : active
            ? 'border-[var(--hc-accent)]/60 bg-[var(--hc-accent)]/12 text-[var(--hc-accent)]'
            : 'border-transparent text-[var(--hc-muted)] hover:border-[var(--hc-line)] hover:bg-[var(--hc-surface-2)] hover:text-[var(--hc-ink)]'
      }`}
    >
      <Icon name={icon} size={17} />
      <span className="scale-90 leading-none">{label}</span>
      {badge ? (
        <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-[var(--hc-amber)] px-1 text-[9px] font-semibold text-[#241703]">
          {badge > 99 ? '99+' : badge}
        </span>
      ) : null}
    </button>
  )
}

function useRail() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuth((state) => state.user)
  const pendingCount = useData((state) => state.pendingCount)
  const selectedId = useData((state) => state.selectedId)
  const fields = useData((state) => state.fields)
  const mode = useWork((state) => state.mode)
  const setRailOpen = useUI((state) => state.setRailOpen)

  const path = location.pathname
  const selected = fields.find((field) => field.id === selectedId)

  const nav = (
    <>
      <RailButton icon="map" label="地图" active={path === '/'} onClick={() => navigate('/')} />
      <RailButton
        icon="fields"
        label="田块"
        active={path.startsWith('/fields')}
        onClick={() => navigate('/fields')}
        badge={pendingCount}
      />
      <RailButton
        icon="history"
        label="记录"
        active={path.startsWith('/history')}
        onClick={() => navigate('/history')}
      />
      {user?.role === 'admin' && (
        <RailButton
          icon="users"
          label="管理"
          active={path.startsWith('/admin')}
          onClick={() => navigate('/admin')}
        />
      )}
    </>
  )

  const tools = (
    <>
      <RailButton icon="scan" label="识别" primary onClick={() => void recognizeCurrentView()} />
      <RailButton
        icon="draw"
        label="勾画"
        active={mode === 'draw'}
        onClick={() => {
          navigate('/')
          useWork.getState().startDraw()
          setRailOpen(false)
        }}
      />
      <RailButton icon="pencil" label="编辑" active={mode === 'edit'} onClick={() => void editGeometry(selected)} />
      <RailButton icon="locate" label="定位" onClick={locateMe} />
    </>
  )

  return { nav, tools }
}

export function DesktopRail() {
  const { nav, tools } = useRail()
  return (
    <aside className="z-20 hidden w-16 shrink-0 flex-col items-center gap-1 border-r border-[var(--hc-line)] bg-[var(--hc-surface)] py-2 lg:flex">
      <div className="flex flex-col items-center gap-1">{nav}</div>
      <div className="my-1 h-px w-8 bg-[var(--hc-line)]" />
      <div className="flex flex-col items-center gap-1">{tools}</div>
      <div className="my-1 h-px w-8 bg-[var(--hc-line)]" />
      <RailButton icon="layers" label="底图" onClick={cycleProvider} />
      <div className="mt-auto">
        <RailButton
          icon="refresh"
          label="刷新"
          onClick={() => {
            void useData.getState().load()
            useUI.getState().notify('已刷新田块数据')
          }}
        />
      </div>
    </aside>
  )
}

export function MobileRail() {
  const { nav, tools } = useRail()
  const railOpen = useUI((state) => state.railOpen)
  const setRailOpen = useUI((state) => state.setRailOpen)

  return (
    <div className="absolute bottom-[112px] left-2 z-20 flex flex-col items-start lg:hidden">
      <div className="flex flex-col gap-1 rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)]/95 p-1 shadow-xl backdrop-blur">
        {railOpen ? (
          <>
            {nav}
            <div className="my-0.5 h-px w-8 self-center bg-[var(--hc-line)]" />
            {tools}
            <RailButton icon="layers" label="底图" onClick={cycleProvider} />
            <RailButton icon="close" label="收起" onClick={() => setRailOpen(false)} />
          </>
        ) : (
          <>
            {tools}
            <RailButton icon="menu" label="更多" onClick={() => setRailOpen(true)} />
          </>
        )}
      </div>
    </div>
  )
}
