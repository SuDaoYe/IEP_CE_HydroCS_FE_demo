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
    <div className="flex items-center gap-2 px-4 py-2.5 bg-[var(--bg-sidebar)] border-t border-[var(--border)] shrink-0">
      <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mr-1">工具</span>
      {tools.map((tool, i) => (
        <button
          key={i}
          onClick={tool.onClick}
          className={
            tool.primary
              ? 'w-[130px] py-1.5 text-[11px] text-[var(--text-primary)] bg-[var(--tool-btn)] border border-[var(--accent)] rounded-md text-center shrink-0'
              : 'w-[130px] py-1.5 text-[11px] text-[var(--text-body)] bg-[var(--tool-btn)] border border-[var(--border)] rounded-md text-center hover:text-[var(--text-primary)] shrink-0'
          }
        >
          {tool.label}
        </button>
      ))}
    </div>
  )
}
