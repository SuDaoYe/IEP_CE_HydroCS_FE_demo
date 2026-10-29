import { useMemo } from 'react'
import { useData } from '../store/data'
import { useIrrigation } from '../store/irrigation'
import { useUI, type SheetSnap } from '../store/ui'
import { fmtMu, fmtM3 } from '../lib/format'
import { flyToField } from './mapBridge'
import { Empty, Icon, Spinner, Stat } from './ui'

const SNAP: Record<SheetSnap, string> = {
  peek: 'h-[92px]',
  half: 'h-[46dvh]',
  full: 'h-[78dvh]',
}

export default function FieldSheet() {
  const fields = useData((state) => state.fields)
  const selectedId = useData((state) => state.selectedId)
  const select = useData((state) => state.select)
  const summary = useIrrigation((state) => state.summary)
  const loading = useIrrigation((state) => state.summaryLoading)
  const sheet = useUI((state) => state.sheet)
  const setSheet = useUI((state) => state.setSheet)
  const detailOpen = useUI((state) => state.detailOpen)
  const setDetailOpen = useUI((state) => state.setDetailOpen)

  const demandByField = useMemo(() => {
    const map = new Map<string, number>()
    summary?.fields.forEach((entry) => map.set(entry.field.id, entry.totals.volume_m3))
    return map
  }, [summary])

  const totals = summary?.totals
  // Offline (or before the summary arrives) fall back to what we have locally.
  const localCount = fields.length
  const localArea = fields.reduce((sum, field) => sum + field.area_mu, 0)
  const fieldCount = totals ? totals.fields : localCount
  const areaMu = totals ? totals.area_mu : localArea

  function pick(id: string) {
    select(id)
    setDetailOpen(true)
    const field = fields.find((item) => item.id === id)
    if (field) flyToField(field)
    if (window.innerWidth < 1024) setSheet('peek')
  }

  return (
    <section
      className={`z-20 flex shrink-0 flex-col border-[var(--hc-line)] bg-[var(--hc-surface)] transition-[height] duration-200 ease-out max-lg:absolute max-lg:inset-x-0 max-lg:bottom-0 max-lg:rounded-t-2xl max-lg:border-t max-lg:shadow-[0_-18px_44px_-30px_rgba(0,0,0,0.9)] ${SNAP[sheet]} lg:h-[196px] lg:border-t`}
      style={detailOpen ? undefined : undefined}
    >
      <button
        type="button"
        onClick={() => setSheet(sheet === 'peek' ? 'half' : sheet === 'half' ? 'full' : 'peek')}
        className="flex w-full items-center gap-2 px-3.5 pb-1.5 pt-2 lg:cursor-default"
      >
        <span className="mx-auto h-1 w-9 rounded-full bg-[var(--hc-line-strong,#2a3a49)] lg:hidden" />
        <span className="hc-label hidden lg:inline">田块列表</span>
        <span className="ml-auto hidden items-center gap-4 lg:flex">
          {loading ? (
            <Spinner size={12} />
          ) : (
            <>
              <span className="text-[11px] text-[var(--hc-faint)]">
                {fieldCount} 块 · {fmtMu(areaMu)}
              </span>
              <span className="text-[11px] text-[var(--hc-muted)]">
                {summary?.days ?? 7} 天合计{' '}
                <span className="hc-num text-[var(--hc-accent)]">
                  {totals ? fmtM3(totals.week_m3) : '—'}
                </span>
              </span>
            </>
          )}
        </span>
      </button>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {fields.length === 0 ? (
          <Empty
            icon="fields"
            title="还没有田块"
            hint="点左侧“识别”自动圈出周边田块，或用“勾画”手动绘一块。"
          />
        ) : (
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
            {fields.map((field) => {
              const active = field.id === selectedId
              return (
                <button
                  key={field.id}
                  type="button"
                  onClick={() => pick(field.id)}
                  className={`flex items-center gap-3 rounded-xl border px-2.5 py-2 text-left transition ${
                    active
                      ? 'border-[var(--hc-accent)]/70 bg-[var(--hc-accent)]/8'
                      : 'border-[var(--hc-line)] bg-[var(--hc-surface-2)] hover:border-[var(--hc-line-strong,#2a3a49)]'
                  }`}
                >
                  <span
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
                      active ? 'bg-[var(--hc-accent)]/18 text-[var(--hc-accent)]' : 'bg-[var(--hc-canvas)] text-[var(--hc-faint)]'
                    }`}
                  >
                    <Icon name="crop" size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] text-[var(--hc-ink)]">{field.name}</span>
                    <span className="block truncate text-[10.5px] text-[var(--hc-faint)]">
                      {field.crop_label ?? '未录入'} · {field.stage_label ?? '—'} · {fmtMu(field.area_mu)}
                    </span>
                  </span>
                  <span className="text-right">
                    <span className="hc-num block text-[12.5px] text-[var(--hc-ink)]">
                      {demandByField.has(field.id) ? fmtM3(demandByField.get(field.id)!) : '—'}
                    </span>
                    <span className="block text-[9.5px] text-[var(--hc-faint)]">7天</span>
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      <div className="hidden border-t border-[var(--hc-line)] px-3.5 py-2 lg:flex lg:items-center lg:gap-6">
        <Stat
          label="今日需灌（净）"
          value={totals ? fmtM3(totals.daily_net_m3 ?? totals.daily_m3) : '—'}
          accent
          size="sm"
        />
        <Stat label="今日供水（毛）" value={totals ? fmtM3(totals.daily_m3) : '—'} size="sm" />
        <Stat
          label={`${summary?.days ?? 7} 天需灌`}
          value={totals ? fmtM3(totals.week_net_m3 ?? totals.week_m3) : '—'}
          size="sm"
        />
        <Stat
          label={`${summary?.days ?? 7} 天总水量`}
          value={totals ? fmtM3(totals.week_m3) : '—'}
          size="sm"
        />
        <Stat label="覆盖面积" value={fmtMu(areaMu)} size="sm" />
        <span className="ml-auto text-[10px] text-[var(--hc-faint)]">
          净 = 补进根区的水量；毛 = 计入输水/灌溉损失后从水源取的水量
        </span>
      </div>
    </section>
  )
}
