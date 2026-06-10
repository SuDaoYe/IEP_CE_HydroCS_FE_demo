interface Tool {
  label: string
  primary?: boolean
  onClick?: () => void
}

interface Props {
  tools: Tool[]
}

export default function ToolBar({ tools }: Props) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-[#0d1117] border-t border-[#1e2430] shrink-0">
      <span className="text-[9px] text-[#6b7280] uppercase tracking-wider mr-1">工具</span>
      {tools.map((tool, i) => (
        <button
          key={i}
          onClick={tool.onClick}
          className={
            tool.primary
              ? 'w-[130px] py-1.5 text-[11px] text-[#c8ccd0] bg-[#131820] border border-[#818cf8] rounded-md text-center shrink-0'
              : 'w-[130px] py-1.5 text-[11px] text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md text-center hover:text-[#c8ccd0] shrink-0'
          }
        >
          {tool.label}
        </button>
      ))}
    </div>
  )
}
