import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useUI } from '../../store/ui'
import { Empty, Icon, SectionTitle, Spinner, Stat } from '../../components/ui'
import type { FsListing, IngestReport, MeteoStatus } from '../../types'

function ReportCard({ report }: { report: IngestReport | null }) {
  if (!report) return null
  const ok = report.years_ingested.length > 0
  return (
    <div
      className={`rounded-xl border p-3 text-[11px] leading-relaxed ${
        ok
          ? 'border-[var(--hc-accent)]/40 bg-[var(--hc-accent)]/8 text-[var(--hc-ink)]'
          : 'border-[var(--hc-amber)]/40 bg-[var(--hc-amber)]/8 text-[var(--hc-amber)]'
      }`}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon name={ok ? 'check' : 'info'} size={13} />
        {ok
          ? `已导入 ${report.years_ingested.join('、')} 年 · 新增 ${report.dates_added} 天 / 覆盖 ${report.dates_replaced} 天`
          : '没有可导入的完整年份'}
      </div>
      <div className="mt-1 text-[10.5px] text-[var(--hc-muted)]">
        当前数据范围 {report.coverage} · 共 {report.total_dates} 天
      </div>
      {report.skipped.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-[10.5px] text-[var(--hc-faint)]">
          {report.skipped.slice(0, 4).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function MeteoPanel() {
  const notify = useUI((state) => state.notify)
  const [status, setStatus] = useState<MeteoStatus | null>(null)
  const [listing, setListing] = useState<FsListing | null>(null)
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [report, setReport] = useState<IngestReport | null>(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    try {
      const payload = await api.adminMeteoStatus()
      setStatus(payload)
      setReport(payload.report)
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function browse(target?: string) {
    setBusy('browse')
    try {
      const payload = await api.adminMeteoFs(target)
      setListing(payload)
      setPath(payload.path)
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  async function scan(target: string) {
    setBusy('scan')
    try {
      const payload = await api.adminMeteoScan(target, true)
      setReport(payload.ingested)
      notify(
        payload.ingested
          ? `扫描到 ${payload.found} 个文件，已导入 ${payload.ingested.years_ingested.join('、') || '无完整年份'}`
          : `扫描到 ${payload.found} 个文件`,
        payload.ingested?.years_ingested.length ? 'success' : 'error',
      )
      await refresh()
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  async function upload(files: FileList | null) {
    if (!files || !files.length) return
    setBusy('upload')
    try {
      const payload = await api.adminMeteoUpload(files)
      setReport(payload.ingested)
      notify(
        payload.ingested
          ? `已上传 ${payload.saved.length} 个文件并导入 ${payload.ingested.years_ingested.join('、') || '无完整年份'}`
          : `已保存 ${payload.saved.length} 个文件`,
        'success',
      )
      await refresh()
    } catch (error) {
      notify((error as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  const domain = status?.cube.domain ?? {}
  const hasCube = Boolean(status?.cube.available)

  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle
          right={
            <button
              type="button"
              onClick={() => void refresh()}
              className="hc-btn h-7 px-2 text-[10.5px]"
              disabled={Boolean(busy)}
            >
              <Icon name="refresh" size={11} /> 刷新
            </button>
          }
        >
          气象数据状态
        </SectionTitle>

        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[11px] text-[var(--hc-faint)]">
            <Spinner size={13} /> 读取中…
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
            <Stat
              label="ERA5 日尺度立方"
              value={hasCube ? String(domain.days ?? '—') : '未加载'}
              unit="天"
              hint={hasCube ? `${domain.start} → ${domain.end}` : status?.cube.error ?? ''}
              accent={hasCube}
              size="sm"
            />
            <Stat label="收件箱文件" value={status?.files ?? 0} unit="个" hint={status?.inbox} size="sm" />
            <Stat
              label="已识别年份"
              value={status ? Object.keys(status.years).join('/') || '—' : '—'}
              size="sm"
            />
            <Stat
              label="行政区库"
              value={status?.divisions?.available ? '已加载' : '未生成'}
              size="sm"
            />
          </div>
        )}
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle>上传 NetCDF 文件</SectionTitle>
          <p className="mb-2 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
            H5 页面只能选择文件、不能选择文件夹。上传后服务端会把文件放进收件箱，
            按年份配对 8 个变量（t2m / d2m / u10 / v10 / sp / tp / ssr / str），
            完整年份才会重算并合并进日尺度立方。
          </p>
          <label className="hc-btn w-full cursor-pointer">
            {busy === 'upload' ? <Spinner size={13} /> : <Icon name="plus" size={13} />}
            选择 .nc 文件上传
            <input
              type="file"
              multiple
              accept=".nc,.nc4,.netcdf"
              className="hidden"
              onChange={(event) => void upload(event.target.files)}
            />
          </label>
          <button
            type="button"
            onClick={async () => {
              setBusy('rebuild')
              try {
                setReport(await api.adminMeteoRebuild())
                notify('已按收件箱重建', 'success')
                await refresh()
              } catch (error) {
                notify((error as Error).message, 'error')
              } finally {
                setBusy(null)
              }
            }}
            className="hc-btn mt-2 w-full text-[11.5px]"
            disabled={Boolean(busy) || !status?.files}
          >
            {busy === 'rebuild' ? <Spinner size={12} /> : <Icon name="refresh" size={12} />}
            用收件箱文件重建立方
          </button>
        </section>

        <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
          <SectionTitle>扫描服务器文件夹</SectionTitle>
          <p className="mb-2 text-[10.5px] leading-relaxed text-[var(--hc-faint)]">
            选择一个服务器上的目录（例如你把 ERA5 压缩包解压到的地方），服务端会递归找出
            <span className="hc-num"> *.nc </span>并复制进收件箱后导入。
          </p>
          <div className="flex gap-1.5">
            <input
              value={path}
              onChange={(event) => setPath(event.target.value)}
              placeholder="例如 D:\\data\\era5"
              className="hc-input h-9 flex-1 text-[11.5px]"
            />
            <button
              type="button"
              onClick={() => void browse(path || undefined)}
              className="hc-btn h-9 px-2 text-[11px]"
              disabled={Boolean(busy)}
            >
              {busy === 'browse' ? <Spinner size={12} /> : <Icon name="fields" size={12} />}
              浏览
            </button>
          </div>

          {listing && (
            <div className="mt-2 rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface-2)]">
              <div className="flex items-center gap-1 border-b border-[var(--hc-line)] px-2 py-1.5 text-[10px] text-[var(--hc-faint)]">
                {listing.parents.slice(-3).map((parent) => (
                  <button
                    key={parent.path}
                    type="button"
                    onClick={() => void browse(parent.path)}
                    className="truncate hover:text-[var(--hc-ink)]"
                  >
                    {parent.name}/
                  </button>
                ))}
                <span className="ml-auto hc-num">{listing.nc_count ?? 0} 个 .nc</span>
              </div>
              <ul className="max-h-[180px] overflow-y-auto py-1">
                {listing.entries.slice(0, 60).map((entry) => (
                  <li key={entry.path}>
                    <button
                      type="button"
                      onClick={() => (entry.type === 'dir' ? void browse(entry.path) : undefined)}
                      className="flex w-full items-center gap-1.5 px-2 py-1 text-left text-[11px] text-[var(--hc-muted)] hover:bg-[var(--hc-surface)]"
                    >
                      <Icon
                        name={entry.type === 'dir' ? 'fields' : 'layers'}
                        size={11}
                        className="shrink-0 text-[var(--hc-faint)]"
                      />
                      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                      {entry.type === 'dir' && <Icon name="chevron" size={10} className="-rotate-90" />}
                    </button>
                  </li>
                ))}
                {listing.entries.length === 0 && (
                  <li className="px-2 py-3 text-center text-[10.5px] text-[var(--hc-faint)]">
                    没有子目录或 .nc 文件
                  </li>
                )}
              </ul>
              <div className="border-t border-[var(--hc-line)] p-1.5">
                <button
                  type="button"
                  onClick={() => void scan(listing.path)}
                  className="hc-btn hc-btn-primary h-8 w-full text-[11.5px]"
                  disabled={Boolean(busy) || !listing.nc_count}
                >
                  {busy === 'scan' ? <Spinner size={12} /> : <Icon name="check" size={12} />}
                  扫描并导入此目录
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="rounded-2xl border border-[var(--hc-line)] bg-[var(--hc-surface)] p-3.5">
        <SectionTitle>最近一次导入</SectionTitle>
        {report ? (
          <ReportCard report={report} />
        ) : (
          <Empty icon="history" title="本次会话还没有导入记录" hint="上传文件或扫描目录后会在这里显示结果。" />
        )}
        {status?.warnings?.length ? (
          <ul className="mt-2 list-disc pl-4 text-[10.5px] text-[var(--hc-faint)]">
            {status.warnings.slice(0, 6).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
        <p className="mt-2 text-[10px] leading-relaxed text-[var(--hc-faint)]">
          目标文件：<span className="hc-num">{status?.target}</span>
          。导入是幂等的：同一年的文件重复导入只会覆盖对应日期，不会产生重复行。
        </p>
      </section>
    </div>
  )
}
