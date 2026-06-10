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
    <div className="w-[200px] bg-[#0d1117] border-r border-[#1e2430] flex flex-col shrink-0">
      <div className="px-3 pt-3 pb-2">
        <span className="text-[9px] text-[#6b7280] uppercase tracking-wider">菜单</span>
      </div>
      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onSelect(item.key)}
          className={
            item.key === activeKey
              ? 'mx-2 my-0.5 px-3 py-2 text-xs text-[#c8ccd0] bg-[rgba(129,140,248,0.08)] border-l-2 border-[#818cf8] rounded-r text-left'
              : 'mx-2 my-0.5 px-3 py-2 text-xs text-[#9ca3af] hover:text-[#c8ccd0] text-left rounded'
          }
        >
          {item.icon && <span className="mr-2">{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  )
}
