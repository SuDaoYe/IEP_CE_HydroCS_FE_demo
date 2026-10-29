import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { fmtDate, fmtMm, fmtMu, fmtM3, fmtNumber } from '../lib/format'
import { editGeometry } from '../lib/actions'
import { useData } from '../store/data'
import { useIrrigation } from '../store/irrigation'
import { useUI } from '../store/ui'
import { Empty, Icon, Spinner, Stat } from '../components/ui'
import IrrigationChart from '../components/IrrigationChart'
import { flyToField } from '../components/mapBridge'

export default function MyFields() {
  const navigate = useNavigate()
  const fields = useData((state) => state.fields)
  const loading = useData((state) => state.loading)
  const select = useData((state) => state.select)
  const loadFields = useData((state) => state.load)
  const summary = useIrrigation((state) => state.summary)
  const loadSummary = useIrrigation((state) => state.loadSummary)
  const setDetailOpen = useUI((state) => state.setDetailOpen)

  // 直接刷新/深链进入本页时 store 是空的，必须主动拉一次
  useEffect(() => {
    void loadFields()
    void loadSummary()
  }, [loadFields, loadSummary])

  const totals = summary?.totals

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6">
      <div className="mx-auto max-w-[980px]">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[17px] font-semibold text-[var(--hc-ink)]">我的田块</h1>
            <p className="mt-1 text-[11.5px] text-[var(--hc-faint)]">
              每块地的面积、作物生育期与未来一段时间的灌溉需水量（合计都标注了统计天数）
            </p>
          </div>
          <div className="flex gap-5">
            <Stat label="田块数" value={fields.length} size="sm" />
            <Stat label="总面积" value={fmtMu(totals?.area_mu ?? 0)} size="sm" />
            <Stat
              label={`${summary?.days ?? 7} 天需水`}
              value={fmtM3(totals?.week_m3 ?? 0)}
              accent
              size="sm"
            />
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-24 text-[12px] text-[var(--hc-faint)]">
            <Spinner size={14} /> 加载田块…
          </div>
        ) : fields.length === 0 ? (
          <Empty icon="fields" title="还没有田块" hint="回到地图，识别或勾画一块田并保存。" />
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {fields.map((field) => {
              const entry = summary?.fields.find((item) => item.field.id === field.id)
              return (
                <article
                  key={field.id}
                  className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="truncate text-[13.5px] font-medium text-[var(--hc-ink)]">{field.name}</h2>
                      <p className="mt-0.5 text-[10.5px] text-[var(--hc-faint)]">
                        {field.crop_label ?? '未录入作物'} · {field.stage_label ?? '—'} ·{' '}
                        {field.plant_date ? `播于 ${fmtDate(field.plant_date)}` : '未填播种日期'}
                      </p>
                    </div>
                    <span className="hc-chip shrink-0">{fmtMu(field.area_mu)}</span>
                  </div>

                  {entry ? (
                    <div className="mt-3">
                      <div className="flex items-end justify-between gap-2">
                        <div className="flex gap-3">
                          <Stat
                            label={`${summary?.days ?? 7} 天需灌（净）`}
                            value={fmtM3(entry.totals.net_volume_m3 ?? entry.totals.volume_m3)}
                            accent
                            size="md"
                          />
                          <Stat
                            label={`${summary?.days ?? 7} 天总水量（毛）`}
                            value={fmtM3(entry.totals.volume_m3)}
                            size="md"
                          />
                        </div>
                        <div className="text-right text-[10.5px] text-[var(--hc-faint)]">
                          日均供 {fmtM3(entry.totals.daily_avg_m3)}
                          <br />
                          亩均{' '}
                          {entry.totals.per_mu_m3 !== null
                            ? `${fmtNumber(entry.totals.per_mu_m3, 1)} m³`
                            : '—'}
                        </div>
                      </div>
                      <div className="mt-2">
                        <IrrigationChart series={entry.series} height={76} compact />
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-2 rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface-2)] px-2.5 py-2 text-[10.5px]">
                        <div>
                          <div className="text-[var(--hc-faint)]">本周（净 / 毛）</div>
                          <div className="hc-num text-[var(--hc-ink)]">
                            {fmtM3(entry.aggregates?.weekly[0]?.net_volume_m3 ?? 0)}
                            <span className="text-[var(--hc-faint)]"> / </span>
                            {fmtM3(entry.aggregates?.weekly[0]?.volume_m3 ?? 0)}
                          </div>
                        </div>
                        <div>
                          <div className="text-[var(--hc-faint)]">本月（净 / 毛）</div>
                          <div className="hc-num text-[var(--hc-ink)]">
                            {fmtM3(entry.aggregates?.monthly[0]?.net_volume_m3 ?? 0)}
                            <span className="text-[var(--hc-faint)]"> / </span>
                            {fmtM3(entry.aggregates?.monthly[0]?.volume_m3 ?? 0)}
                          </div>
                        </div>
                        <div>
                          <div className="text-[var(--hc-faint)]">
                            {summary?.days ?? 7} 天有效降雨
                          </div>
                          <div className="hc-num text-[var(--hc-ink)]">
                            {fmtMm(entry.totals.pe_mm ?? 0)}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="py-6 text-center text-[11px] text-[var(--hc-faint)]">暂无解算结果</div>
                  )}

                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        select(field.id)
                        setDetailOpen(true)
                        navigate('/')
                        setTimeout(() => flyToField(field), 240)
                      }}
                      className="hc-btn flex-1 h-9 text-[12px]"
                    >
                      <Icon name="target" size={13} /> 地图查看
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        navigate('/')
                        void editGeometry(field)
                      }}
                      className="hc-btn flex-1 h-9 text-[12px]"
                    >
                      <Icon name="pencil" size={13} /> 改形状
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        )}

        <p className="mt-6 rounded-xl border border-[var(--hc-line)] bg-[var(--hc-surface-2)] p-3 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
          计算说明：ET0 由 ERA5 逐小时气象数据按 FAO-56 Penman–Monteith 计算，有效降雨由 ERA5 日降水估算；
          两者都按田块与 0.25° 网格的面积重叠加权后，再套用作物生育期系数 Kc 与灌溉水利用系数 η 换算需水量。
          日期超出 2000–2004 观测范围时使用同日序气候态，界面会标注。
        </p>
        <div className="h-6" />
      </div>
    </div>
  )
}
