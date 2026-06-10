interface DataItem {
  label: string
  value: string
  highlight?: boolean
  sub?: string
}

interface Props {
  items: DataItem[]
}

export default function DataPanel({ items }: Props) {
  return (
    <div className="w-[260px] bg-[var(--bg-sidebar)] border-l border-[var(--border)] p-3.5 overflow-y-auto shrink-0">
      <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mb-3">数据</div>
      {items.map((item, i) => (
        <div key={i} className="bg-[var(--bg-panel)] border border-[var(--border)] rounded-md p-3 mb-2">
          <div className="text-[10px] text-[var(--text-muted)] mb-1">{item.label}</div>
          <div className={item.highlight ? 'text-2xl font-semibold text-[var(--accent)]' : 'text-lg font-semibold text-[var(--text-primary)]'}>
            {item.value}
          </div>
          {item.sub && <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{item.sub}</div>}
        </div>
      ))}
    </div>
  )
}
