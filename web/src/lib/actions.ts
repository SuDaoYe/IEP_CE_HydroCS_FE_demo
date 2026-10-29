import { api } from './api'
import { currentViewBBox, flyToPoint } from '../components/mapBridge'
import { useData } from '../store/data'
import { useUI } from '../store/ui'
import { useWork } from '../store/work'
import type { Field } from '../types'

export async function recognizeCurrentView(): Promise<void> {
  const bbox = currentViewBBox()
  if (!bbox) {
    useUI.getState().notify('地图尚未就绪，请稍候', 'error')
    return
  }
  const ui = useUI.getState()
  ui.setBusy('正在识别田块…')
  useWork.setState({ segmentError: null })
  try {
    const result = await api.segment({
      bbox,
      provider: useUI.getState().provider,
    })
    useWork.getState().setCandidates(
      result.features,
      {
        backend: result.backend,
        coverage: result.coverage_pct,
        count: result.count,
        totalAreaHa: result.total_area_ha,
        zoom: result.zoom,
        mpp: result.image.mpp_x,
        cached: Boolean(result.cached),
      },
      result.error,
    )
    if (result.count === 0) {
      useUI.getState().notify('这一区域没有识别到明显田块，请放大或换个位置', 'info')
    } else {
      useUI
        .getState()
        .notify(
          `识别到 ${result.count} 块田（${result.total_area_ha.toFixed(1)} 公顷），点选以采纳`,
          'success',
        )
    }
  } catch (error) {
    const message = (error as Error).message
    useWork.getState().setCandidates([], null, message)
    useUI.getState().notify(message, 'error')
  } finally {
    useUI.getState().setBusy(null)
  }
}

export function locateMe(): void {
  if (!navigator.geolocation) {
    useUI.getState().notify('当前浏览器不支持定位', 'error')
    return
  }
  useUI.getState().setBusy('正在定位…')
  navigator.geolocation.getCurrentPosition(
    (position) => {
      const { longitude, latitude } = position.coords
      // Warm the tile cache *before* flying: otherwise the map looks blank for
      // seconds while 30+ cold tiles are pulled from the vendor.
      warmView(longitude, latitude, 16)
      flyToPoint(longitude, latitude, 16)
      useUI.getState().setBusy(null)
      useUI.getState().notify('已定位，正在加载该区域影像…')
    },
    () => {
      useUI.getState().setBusy(null)
      useUI.getState().notify('定位失败，请检查浏览器权限', 'error')
    },
    { enableHighAccuracy: true, timeout: 8000 },
  )
}

/** Ask the server to pre-cache tiles around a point (fire and forget). */
export function warmView(lon: number, lat: number, zoom: number): void {
  const provider = useUI.getState().provider
  void api.imageryWarm(lon, lat, Math.round(zoom), provider).catch(() => undefined)
}

export async function syncNow(): Promise<void> {
  const store = useData.getState()
  if (!store.pendingCount) {
    useUI.getState().notify('没有待同步的改动')
    return
  }
  useUI.getState().setBusy('正在同步离线改动…')
  try {
    const result = await store.sync()
    useUI
      .getState()
      .notify(
        `同步完成：${result.applied} 条生效${result.conflicts ? `，${result.conflicts} 条冲突` : ''}`,
        result.conflicts ? 'error' : 'success',
      )
  } catch (error) {
    useUI.getState().notify((error as Error).message, 'error')
  } finally {
    useUI.getState().setBusy(null)
  }
}

export async function editGeometry(field: Field | undefined): Promise<void> {
  if (!field) {
    useUI.getState().notify('请先在地图或列表中选择一块田', 'error')
    return
  }
  useWork.getState().startEdit(field)
  useUI.getState().setSheet('peek')
}

const PROVIDER_ORDER = ['esri', 'amap', 'sentinel2'] as const

export function cycleProvider(): void {
  const ui = useUI.getState()
  const index = PROVIDER_ORDER.indexOf(ui.provider as (typeof PROVIDER_ORDER)[number])
  const next = PROVIDER_ORDER[(index + 1) % PROVIDER_ORDER.length]
  ui.setProvider(next)
  const labels: Record<string, string> = {
    esri: 'Esri 高清影像',
    amap: '高德卫星影像',
    sentinel2: 'Sentinel-2 时序',
  }
  ui.notify(`底图切换：${labels[next]}`)
}
