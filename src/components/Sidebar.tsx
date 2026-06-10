interface MenuItem {
  key: string
  label: string
  active?: boolean
  icon?: string
}

interface Props {
  items: MenuItem[]
  activeKey: string
  onSelect: (key: string) => void
}

export default function Sidebar({ items, activeKey, onSelect }: Props) {
  return (
    <div className="w-[200px] bg-[var(--bg-sidebar)] border-r border-[var(--border)] flex flex-col shrink-0">
      <div className="px-3 pt-3 pb-2">
        <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider">菜单</span>
      </div>
      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onSelect(item.key)}
          className={
            item.key === activeKey
              ? 'mx-2 my-0.5 px-3 py-2 text-xs text-[var(--text-primary)] bg-[var(--accent-bg)] border-l-2 border-[var(--accent)] rounded-r text-left'
              : 'mx-2 my-0.5 px-3 py-2 text-xs text-[var(--text-body)] hover:text-[var(--text-primary)] text-left rounded'
          }
        >
          {item.icon && <span className="mr-2">{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  )
}
