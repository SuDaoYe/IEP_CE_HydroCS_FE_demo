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
    <div className="w-[260px] bg-[#0d1117] border-l border-[#1e2430] p-3.5 overflow-y-auto shrink-0">
      <div className="text-[9px] text-[#6b7280] uppercase tracking-wider mb-3">数据</div>
      {items.map((item, i) => (
        <div key={i} className="bg-[#131820] border border-[#1e2430] rounded-md p-3 mb-2">
          <div className="text-[10px] text-[#6b7280] mb-1">{item.label}</div>
          <div className={item.highlight ? 'text-2xl font-semibold text-[#818cf8]' : 'text-lg font-semibold text-[#c8ccd0]'}>
            {item.value}
          </div>
          {item.sub && <div className="text-[10px] text-[#6b7280] mt-0.5">{item.sub}</div>}
        </div>
      ))}
    </div>
  )
}
