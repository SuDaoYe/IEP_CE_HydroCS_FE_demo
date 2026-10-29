import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import { useUI } from '../../store/ui'
import RegionPicker from '../../components/RegionPicker'
import { Empty, Icon, SectionTitle, Spinner, Stat } from '../../components/ui'
import type { ParamScope, RegionHit } from '../../types'

const SCOPE_LABEL: Record<string, string> = {
  global: '全局默认',
  province: '省级',
  city: '市级',
  default: '内置默认',
}

/** 系数按行政区继承：全局 → 省 → 市。这里是它的编辑台。 */
export default function ParamPanel() {
  const notify = useUI((state) => state.notify)
  const [scope, setScope] = useState('global')
  const [data, setData] = useState<ParamScope | null>(null)
  const [draft, setDraft] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(
    async (target: string) => {
      setLoading(true)
      try {
        const payload = await api.adminParams(target)
        setData(payload)
        setDraft(payload.values)
      } catch (error) {
        notify((error as Error).message, 'error')
      } finally {
        setLoading(false)
      }
    },
    [notify],
  )

  useEffect(() => {
    void load(scope)
  }, [scope, load])

  function pickRegion(hit: RegionHit) {
    if (hit.level === 'province') {
      setScope(`province:${hit.adcode}`)
    } else if (hit.level === 'city') {
      setScope(`city:${hit.adcode}`)
    } else if (hit.parent) {
      // 区县没有独立作用域：用其所属地级市
      setScope(`city:${hit.parent}`)
    } else {
      notify('该级别没有独立参数作用域', 'error')
    }
  }

  const ownOverrides = data?.overrides[data.scope] ?? {}
  const dirty = useMemo(() => {
    if (!data) return false
    return Object.keys(draft).some(
      (key) => Math.abs((draft[key] ?? 0) - (data.values[key] ?? 0)) > 1e-6,
    )
  }, [draft, data])

  async function save() {
    if (!data) return
    setSaving(true)
    try {
      const values: Record<string, number> = {}
      for (const spec of data.catalog) {
        const next = draft[spec.key]
        if (next === undefined) continue
        if (Math.abs(next - (data.values[spec.key] ?? 0)) > 1e-6) values[spec.key] = next
      }
      if (!Object.keys(values).length) {
        notify('没有改动')
        return
      }
      const updated = await api.adminUpdateParams(data.scope, values)
      setData(updated)
      setDraft(updated.values)
      notify(`已保存到 ${scopeName(updated)}`, 'success')
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function clearKey(key: string) {
    if (!data) return
    setSaving(true)
    try {
      const updated = await api.adminUpdateParams(data.scope, { [key]: null })
      setData(updated)
      setDraft(updated.values)
      notify('已清除本层覆盖，回退到上一层')
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setSaving(false)
    }
  }

  function scopeName(payload: ParamScope) {
    if (payload.kind === 'global') return '全局默认'
    return payload.region?.fullname ?? payload.scope
  }

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 py-10 text-[12px] text-[var(--hc-faint)]">
        <Spinner size={14} /> 读取参数…
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle
          right={
            <button
              type="button"
              onClick={() => setScope('global')}
              className={`hc-btn h-7 px-2 text-[10.5px] ${scope === 'global' ? 'border-[var(--hc-accent)]/60 text-[var(--hc-accent)]' : ''}`}
            >
              <Icon name="map" size={11} /> 全局默认
            </button>
          }
        >
          作用域
        </SectionTitle>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <RegionPicker
            onPick={pickRegion}
            placeholder="搜索省或市，为该地区设定参数"
            className="w-full sm:max-w-[420px]"
          />
          <div className="flex flex-wrap items-center gap-1">
            {data?.chain.map((level, index) => (
              <span key={level} className="flex items-center gap-1">
                {index > 0 && <Icon name="chevron" size={10} className="-rotate-90 text-[var(--hc-faint)]" />}
                <button
                  type="button"
                  onClick={() => setScope(level)}
                  className={`hc-chip ${level === data.scope ? 'border-[var(--hc-accent)]/60 text-[var(--hc-accent)]' : ''}`}
                >
                  {level === 'global'
                    ? '全局'
                    : level.startsWith('province:')
                      ? '省级'
                      : level.startsWith('city:')
                        ? '市级'
                        : level}
                </button>
              </span>
            ))}
          </div>
        </div>

        <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
          这些系数本质上是彭曼公式在不同气候区的标定值：华北冬小麦区的 Kc 与降雨利用系数
          和西北干旱灌区、南方稻作区并不相同，所以按行政区层级继承。当前编辑
          <span className="text-[var(--hc-ink)]"> {scopeName(data!)} </span>
          ，未覆盖的参数自动继承上一层。
        </p>
      </section>

      {data && (
        <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle
            right={
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[var(--hc-faint)]">
                  本层覆盖 {Object.keys(ownOverrides).length} 项
                </span>
                <button
                  type="button"
                  onClick={() => void save()}
                  className="hc-btn h-8 text-[11px]"
                  disabled={saving || !dirty}
                >
                  {saving ? <Spinner size={12} /> : <Icon name="check" size={12} />} 保存本层
                </button>
              </div>
            }
          >
            {scopeName(data)} · 生效参数
          </SectionTitle>

          <div className="flex flex-col gap-3">
            {data.catalog.map((spec) => {
              const source = data.sources[spec.key] ?? 'default'
              const inherited = source !== data.scope
              const hasOwn = spec.key in ownOverrides
              return (
                <div
                  key={spec.key}
                  className="rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11.5px] text-[var(--hc-ink)]">{spec.label}</span>
                    <span className="hc-chip shrink-0 text-[9.5px]">{spec.group}</span>
                    <span
                      className={`hc-chip shrink-0 text-[9.5px] ${
                        inherited ? 'text-[var(--hc-faint)]' : 'border-[var(--hc-accent)]/50 text-[var(--hc-accent)]'
                      }`}
                    >
                      {inherited ? `继承 ${SCOPE_LABEL[source.split(':')[0]] ?? source}` : '本层覆盖'}
                    </span>
                    {hasOwn && (
                      <button
                        type="button"
                        onClick={() => void clearKey(spec.key)}
                        className="ml-auto text-[10px] text-[var(--hc-faint)] hover:text-[var(--hc-danger)]"
                        disabled={saving}
                      >
                        清除覆盖
                      </button>
                    )}
                  </div>

                  <div className="mt-1.5 flex items-center gap-2">
                    <input
                      type="number"
                      step={spec.step}
                      min={spec.min}
                      max={spec.max}
                      value={draft[spec.key] ?? ''}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, [spec.key]: Number(event.target.value) }))
                      }
                      className="hc-input h-8 w-[120px] text-[12px]"
                    />
                    <span className="text-[9.5px] text-[var(--hc-faint)]">
                      范围 {spec.min}–{spec.max} · 默认 {spec.default}
                    </span>
                  </div>
                  <p className="mt-1 text-[10px] leading-relaxed text-[var(--hc-faint)]">{spec.hint}</p>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle>已设覆盖的区域</SectionTitle>
        {data?.scopes.length ? (
          <ul className="flex flex-col">
            {data.scopes.map((item) => (
              <li
                key={item.scope}
                className="flex items-center gap-2 border-b border-[var(--hc-line)] py-1.5 text-[11.5px] last:border-0"
              >
                <span className="text-[var(--hc-ink)]">{item.name ?? item.scope}</span>
                <span className="hc-chip">{SCOPE_LABEL[item.kind] ?? item.kind}</span>
                <span className="hc-num text-[var(--hc-faint)]">{item.adcode}</span>
                <span className="hc-num ml-auto text-[var(--hc-muted)]">{item.overrides} 项</span>
                <button
                  type="button"
                  onClick={() => setScope(item.scope)}
                  className="text-[10.5px] text-[var(--hc-sky)]"
                >
                  编辑
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            icon="settings"
            title="还没有区域级覆盖"
            hint="选择某个省或市，把当地的 Kc 校准、降雨利用系数、灌溉水利用系数改成本地经验值。"
          />
        )}
        <div className="mt-2 flex gap-3 text-[10px] text-[var(--hc-faint)]">
          <Stat label="内置默认" value={Object.keys(data?.defaults ?? {}).length} unit="项" size="sm" />
          <Stat label="区域覆盖" value={data?.scopes.length ?? 0} unit="处" size="sm" />
        </div>
      </section>
    </div>
  )
}
