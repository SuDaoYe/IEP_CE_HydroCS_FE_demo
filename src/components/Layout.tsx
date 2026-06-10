import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import ToolBar from './ToolBar'
import DataPanel from './DataPanel'

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
  return (
    <div className="flex flex-col h-screen bg-[#0a0e17] text-[#c8ccd0]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-2.5 bg-[#131820] border-b border-[#1e2430] shrink-0">
        <h1 className="text-sm font-semibold text-[#c8ccd0]">{title}</h1>
        <div className="flex items-center gap-4">
          <span className={`text-xs ${isAdmin ? 'text-amber-400' : 'text-[#9ca3af]'}`}>
            {username}
          </span>
          <button onClick={onLogout} className="text-xs text-[#6b7280] hover:text-[#9ca3af]">退出</button>
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
