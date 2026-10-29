import { useEffect, useState } from 'react'
import MapCanvas from '../components/MapCanvas'
import { DEFAULT_CENTER, DEFAULT_ZOOM } from '../components/mapStyle'
import { warmView } from '../lib/actions'
import { MobileRail } from '../components/ToolRail'
import FieldSheet from '../components/FieldSheet'
import DetailPanel from '../components/DetailPanel'
import { EditPanelDocked, EditPanelMobile } from '../components/EditPanel'
import { useData } from '../store/data'
import { useIrrigation } from '../store/irrigation'
import { useWork } from '../store/work'
import { useUI } from '../store/ui'
import { Icon } from '../components/ui'

export default function Workspace() {
  const load = useData((state) => state.load)
  const fields = useData((state) => state.fields)
  const selectedId = useData((state) => state.selectedId)
  const loadSummary = useIrrigation((state) => state.loadSummary)
  const planFor = useIrrigation((state) => state.planFor)
  const loadPlan = useIrrigation((state) => state.loadPlan)
  const setDetailOpen = useUI((state) => state.setDetailOpen)
  const candidates = useWork((state) => state.candidates)
  const segmentMeta = useWork((state) => state.segmentMeta)
  const clearCandidates = useWork((state) => state.clearCandidates)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Warm the default view so the very first paint is not blank.
    warmView(DEFAULT_CENTER[0], DEFAULT_CENTER[1], DEFAULT_ZOOM)
    void (async () => {
      await load()
      await loadSummary()
      setReady(true)
    })()
  }, [load, loadSummary])

  // Keep the selected parcel's plan in sync with list refreshes.
  useEffect(() => {
    if (selectedId && planFor !== selectedId) void loadPlan(selectedId)
  }, [selectedId, planFor, loadPlan])

  // Opening a parcel on mobile should reveal the detail drawer.
  useEffect(() => {
    if (selectedId && window.innerWidth < 1024) setDetailOpen(true)
  }, [selectedId, setDetailOpen])

  return (
    <div className="relative flex min-h-0 flex-1">
      {/* Docked editor column: on desktop it sits beside the map instead of
          floating over it, which is what used to block the view. */}
      <EditPanelDocked />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="relative min-h-0 flex-1">
          <MapCanvas />
          <MobileRail />
          <EditPanelMobile />

        {/* recognition outcome chip */}
        {segmentMeta && candidates.length > 0 && (
          <div className="absolute left-2 top-2 z-10 max-w-[70%] rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface)]/95 px-3 py-2 shadow-lg backdrop-blur lg:left-3 lg:top-3">
            <div className="flex items-center gap-2">
              <Icon name="scan" size={13} className="text-[var(--hc-amber)]" />
              <span className="text-[11.5px] text-[var(--hc-ink)]">
                识别 {segmentMeta.count} 块 · {segmentMeta.totalAreaHa.toFixed(1)} ha
              </span>
              <button
                type="button"
                onClick={clearCandidates}
                className="ml-1 text-[var(--hc-faint)] hover:text-[var(--hc-ink)]"
                aria-label="清除识别结果"
              >
                <Icon name="close" size={12} />
              </button>
            </div>
            <div className="mt-1 text-[10px] leading-relaxed text-[var(--hc-faint)]">
              {segmentMeta.backend === 'yolo11s-seg' ? 'YOLO11s-seg' : '规则识别（未加载模型）'} ·{' '}
              {segmentMeta.mpp.toFixed(2)} m/px
              {segmentMeta.coverage !== null ? ` · 覆盖 ${segmentMeta.coverage.toFixed(0)}%` : ''}
              {segmentMeta.cached ? ' · 缓存' : ''}
            </div>
            <div className="mt-1 text-[10px] text-[var(--hc-amber)]">点选黄色候选田块即可采纳</div>
          </div>
        )}

        {/* empty state hint */}
        {ready && fields.length === 0 && candidates.length === 0 && (
          <div className="pointer-events-none absolute inset-x-0 top-1/2 z-10 flex -translate-y-1/2 justify-center px-6">
            <div className="max-w-[300px] rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)]/95 p-4 text-center shadow-2xl backdrop-blur">
              <Icon name="scan" size={22} className="mx-auto text-[var(--hc-accent)]" />
              <div className="mt-2 text-[13px] font-medium text-[var(--hc-ink)]">先识别，再修正</div>
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--hc-muted)]">
                把地图移到自家地块上方，点左侧「识别」，模型会圈出周边田块；点中候选即可采纳，再拖动顶点微调。
              </p>
            </div>
          </div>
        )}
        </div>

        <FieldSheet />
      </div>

      <DetailPanel />
    </div>
  )
}
