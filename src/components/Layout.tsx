import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import ToolBar from './ToolBar'
import DataPanel from './DataPanel'
import { useTheme } from '../store/ThemeContext'

interface Props {
  children: ReactNode
  menuItems: { key: string; label: string; active?: boolean; icon?: string }[]
  activeMenu: string
  onMenuClick: (key: string) => void
  panelItems: { label: string; value: string; highlight?: boolean; sub?: string }[]
  tools: { label: string; primary?: boolean; onClick?: () => void }[]
  username: string
  title: string
  isAdmin?: boolean
  onLogout: () => void
}

export default function Layout({
  children, menuItems, activeMenu, onMenuClick,
  panelItems, tools, username, title, isAdmin, onLogout,
}: Props) {
  const { isDark, toggle } = useTheme()
  return (
    <div className="flex flex-col h-screen bg-[var(--bg-page)] text-[var(--text-primary)]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-2.5 bg-[var(--bg-topbar)] border-b border-[var(--border)] shrink-0">
        <h1 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h1>
        <div className="flex items-center gap-4">
          <span className={`text-xs ${isAdmin ? 'text-[var(--warning)]' : 'text-[var(--text-body)]'}`}>
            {username}
          </span>
          <button onClick={toggle} className="text-xs px-2.5 py-1 bg-[var(--border)] rounded text-[var(--text-body)] hover:text-[var(--text-primary)]">
            {isDark ? '☀️ 亮色' : '🌙 暗色'}
          </button>
          <button onClick={onLogout} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-body)]">退出</button>
        </div>
      </div>
      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar items={menuItems} activeKey={activeMenu} onSelect={onMenuClick} />
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-hidden">{children}</div>
          <ToolBar tools={tools} />
        </div>
        <DataPanel items={panelItems} />
      </div>
    </div>
  )
}
