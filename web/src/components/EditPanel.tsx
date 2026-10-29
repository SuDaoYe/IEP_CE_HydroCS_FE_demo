import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { geodesicArea, m2ToMu } from '../lib/geo'
import { fmtMu, fmtNumber } from '../lib/format'
import { useData } from '../store/data'
import { useEditor } from '../store/editor'
import { useWork } from '../store/work'
import { Icon, Spinner } from './ui'

/** Keeps the shared form in sync with the parcel being edited. */
function useHydrate() {
  const mode = useWork((state) => state.mode)
  const editingId = useWork((state) => state.editingId)
  const fields = useData((state) => state.fields)
  const hydrate = useEditor((state) => state.hydrate)
  const setCrops = useEditor((state) => state.setCrops)
  const reset = useEditor((state) => state.reset)

  useEffect(() => {
    api.crops().then(setCrops).catch(() => setCrops([]))
  }, [setCrops])

  useEffect(() => {
    if (mode === 'idle') {
      reset()
      return
    }
    const field = editingId ? fields.find((item) => item.id === editingId) ?? null : null
    hydrate(field, fields.length + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, editingId])
}

function ModeHeader() {
  const mode = useWork((state) => state.mode)
  const label = mode === 'draw' ? '勾画田块' : mode === 'review' ? '确认轮廓' : '调整形状'
  const icon = mode === 'draw' ? 'draw' : 'pencil'
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Icon name={icon} size={14} className="shrink-0 text-[var(--hc-amber)]" />
      <span className="truncate text-[12.5px] font-medium text-[var(--hc-ink)]">{label}</span>
      <span className="hc-chip shrink-0">{mode === 'draw' ? '点按加点' : '拖动顶点'}</span>
    </div>
  )
}

function AreaReadout() {
  const draft = useWork((state) => state.draft)
  const area = draft.length >= 3 ? geodesicArea(draft) : 0
  return (
    <div className="flex items-baseline gap-2">
      <span className="hc-num text-[16px] font-semibold text-[var(--hc-accent)]">
        {fmtMu(m2ToMu(area))}
      </span>
      <span className="text-[10px] text-[var(--hc-faint)]">
        {fmtNumber(area, 0)} m² · {draft.length} 顶点
      </span>
    </div>
  )
}

function Fields() {
  const crops = useEditor((state) => state.crops)
  const name = useEditor((state) => state.name)
  const crop = useEditor((state) => state.crop)
  const stage = useEditor((state) => state.stage)
  const plantDate = useEditor((state) => state.plantDate)
  const setName = useEditor((state) => state.setName)
  const setCrop = useEditor((state) => state.setCrop)
  const setStage = useEditor((state) => state.setStage)
  const setPlantDate = useEditor((state) => state.setPlantDate)
  const cropSpec = crops.find((item) => item.key === crop)

  return (
    <div className="flex flex-col gap-1.5">
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="田块名称"
        className="hc-input h-9 text-[12px]"
      />
      <div className="grid grid-cols-2 gap-1.5">
        <select
          value={crop}
          onChange={(event) => {
            setCrop(event.target.value)
            setStage('')
          }}
          className="hc-input h-9 text-[12px]"
        >
          <option value="">作物…</option>
          {crops.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label}
            </option>
          ))}
        </select>
        <select
          value={stage}
          onChange={(event) => setStage(event.target.value)}
          className="hc-input h-9 text-[12px]"
          disabled={!cropSpec}
        >
          <option value="">生育期…</option>
          {cropSpec?.stages.map((item) => (
            <option key={item.key} value={item.key}>
              {item.label} · {item.kc.toFixed(2)}
            </option>
          ))}
        </select>
      </div>
      <input
        type="date"
        value={plantDate}
        onChange={(event) => setPlantDate(event.target.value)}
        className="hc-input h-9 text-[12px]"
      />
    </div>
  )
}

function Actions({ vertical = false }: { vertical?: boolean }) {
  const mode = useWork((state) => state.mode)
  const draft = useWork((state) => state.draft)
  const editingId = useWork((state) => state.editingId)
  const undoVertex = useWork((state) => state.undoVertex)
  const closeDraft = useWork((state) => state.closeDraft)
  const cancel = useWork((state) => state.cancel)
  const saving = useEditor((state) => state.saving)
  const submit = useEditor((state) => state.submit)

  return (
    <div className={`flex gap-1.5 ${vertical ? 'flex-col' : ''}`}>
      {mode === 'draw' ? (
        <>
          <button type="button" onClick={undoVertex} className="hc-btn flex-1" disabled={!draft.length}>
            <Icon name="refresh" size={13} /> 撤销点
          </button>
          <button
            type="button"
            onClick={closeDraft}
            className="hc-btn hc-btn-primary flex-1"
            disabled={draft.length < 3}
          >
            <Icon name="check" size={13} /> 闭合轮廓
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => void submit()}
          className="hc-btn hc-btn-primary flex-1"
          disabled={saving || draft.length < 3}
        >
          {saving ? <Spinner size={13} /> : <Icon name="check" size={14} />}
          {editingId ? '保存形状' : '保存田块'}
        </button>
      )}
      <button type="button" onClick={cancel} className="hc-btn hc-btn-ghost">
        <Icon name="close" size={13} /> 取消
      </button>
    </div>
  )
}

/** Desktop: a real column beside the map — it never covers the imagery. */
export function EditPanelDocked() {
  useHydrate()
  const mode = useWork((state) => state.mode)
  if (mode === 'idle') return null
  return (
    <aside className="hidden w-[278px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-[var(--hc-line)] bg-[var(--hc-surface)] p-3 lg:flex">
      <ModeHeader />
      <AreaReadout />
      <Fields />
      <Actions vertical />
      <p className="mt-auto text-[10px] leading-relaxed text-[var(--hc-faint)]">
        地图随时可拖动：左键拖 / 中键（滚轮）按下滑动 / 触屏双指；滚轮或双指捏合缩放。
        勾画时点按加点，不会误拖地图。
      </p>
    </aside>
  )
}

/** Mobile: pinned to the bottom edge above the sheet, collapsible. */
export function EditPanelMobile() {
  useHydrate()
  const mode = useWork((state) => state.mode)
  const [expanded, setExpanded] = useState(true)
  if (mode === 'idle') return null
  return (
    <div className="absolute inset-x-2 bottom-[100px] z-30 lg:hidden">
      <div className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)]/97 p-2.5 shadow-2xl backdrop-blur">
        <div className="flex items-center gap-1">
          <ModeHeader />
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="ml-auto shrink-0 text-[var(--hc-faint)]"
            aria-label={expanded ? '收起' : '展开'}
          >
            <Icon name="chevron" size={14} className={expanded ? 'rotate-180' : ''} />
          </button>
        </div>
        <div className="mt-1.5">
          <AreaReadout />
        </div>
        {expanded && (
          <>
            <div className="mt-2">
              <Fields />
            </div>
            <div className="mt-2">
              <Actions />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
