import { useTheme } from '../store/ThemeContext'

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
  const { isDark } = useTheme()

  const colors = {
    sidebarBg: isDark ? '#0d1117' : '#fafafa',
    cardBg: isDark ? '#131820' : '#ffffff',
    border: isDark ? '#1e2430' : '#e5e5e5',
    textPrimary: isDark ? '#c8ccd0' : '#1a1a1a',
    textMuted: isDark ? '#6b7280' : '#999999',
    accent: isDark ? '#818cf8' : '#6366f1',
  }

  return (
    <div className="w-[260px] border-l p-3.5 overflow-y-auto shrink-0" style={{ backgroundColor: colors.sidebarBg, borderColor: colors.border }}>
      <div className="text-[9px] uppercase tracking-wider mb-3" style={{ color: colors.textMuted }}>数据</div>
      {items.map((item, i) => (
        <div key={i} className="border rounded-md p-3 mb-2" style={{ backgroundColor: colors.cardBg, borderColor: colors.border }}>
          <div className="text-[10px] mb-1" style={{ color: colors.textMuted }}>{item.label}</div>
          <div className={item.highlight ? 'text-2xl font-semibold' : 'text-lg font-semibold'} style={{ color: item.highlight ? colors.accent : colors.textPrimary }}>
            {item.value}
          </div>
          {item.sub && <div className="text-[10px] mt-0.5" style={{ color: colors.textMuted }}>{item.sub}</div>}
        </div>
      ))}
    </div>
  )
}
