import type {
  AdminStats,
  Crop,
  Field,
  FsListing,
  HistoryLog,
  IngestReport,
  IrrigationPlan,
  IrrigationSummary,
  MeteoStatus,
  ParamScope,
  PlaceResult,
  ProviderInfo,
  RegionHit,
  RegionOverview,
  RegionSummary,
  SegmentResult,
  TokenResponse,
  User,
} from '../types'

// Same-origin by default (the backend serves web/dist). Set VITE_API_BASE when
// the SPA is hosted elsewhere, e.g. http://192.168.1.20:8000/api/v1
const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '/api/v1'

export class ApiError extends Error {
  status: number
  network: boolean
  constructor(message: string, status: number, network = false) {
    super(message)
    this.status = status
    this.network = network
  }
}

let tokenProvider: () => string | null = () => null

export function setTokenProvider(fn: () => string | null) {
  tokenProvider = fn
}

type ConnectionListener = (offline: boolean) => void
const connectionListeners = new Set<ConnectionListener>()

export function onConnectionChange(listener: ConnectionListener): () => void {
  connectionListeners.add(listener)
  return () => connectionListeners.delete(listener)
}

function reportConnection(offline: boolean) {
  connectionListeners.forEach((listener) => listener(offline))
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const token = tokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch {
    reportConnection(true)
    const where = BASE.startsWith('http') ? BASE : `${window.location.origin}${BASE}`
    throw new ApiError(
      navigator.onLine
        ? `连不上后端 ${where}。请确认服务已启动（在同一台电脑上直接访问 http://127.0.0.1:8000）。`
        : '当前处于离线状态，显示的是本地缓存',
      0,
      true,
    )
  }
  reportConnection(false)

  if (response.status === 204) return undefined as T
  const text = await response.text()
  const payload = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message)) || `请求失败 (${response.status})`
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status)
  }
  return payload as T
}

export const api = {
  // --- auth ---
  login: (username: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  register: (data: { username: string; password: string; name: string; phone?: string }) =>
    request<TokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  me: () => request<User>('/auth/me'),

  // --- fields ---
  listFields: () => request<Field[]>('/fields'),
  getField: (id: string) => request<Field>(`/fields/${id}`),
  createField: (data: Record<string, unknown>) =>
    request<Field>('/fields', { method: 'POST', body: JSON.stringify(data) }),
  updateField: (id: string, data: Record<string, unknown>) =>
    request<Field>(`/fields/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteField: (id: string) => request<void>(`/fields/${id}`, { method: 'DELETE' }),
  irrigation: (id: string, days = 7, start?: string) =>
    request<IrrigationPlan>(
      `/fields/${id}/irrigation?days=${days}${start ? `&start=${start}` : ''}`,
    ),

  // --- recognition & irrigation ---
  segment: (data: {
    bbox: [number, number, number, number]
    zoom?: number
    provider?: string
    min_area_ha?: number
  }) => request<SegmentResult>('/segment', { method: 'POST', body: JSON.stringify(data) }),
  segmentStatus: () =>
    request<{ backend: string; weights_present: boolean; error: string | null }>(
      '/segment/status',
    ),
  crops: () => request<Crop[]>('/irrigation/crops'),
  summary: (days = 7) => request<IrrigationSummary>(`/irrigation/summary?days=${days}`),
  logs: (limit = 40) => request<HistoryLog[]>(`/irrigation/logs?limit=${limit}`),

  // --- imagery ---
  providers: () => request<ProviderInfo[]>('/imagery/providers'),
  imageryWarm: (lon: number, lat: number, zoom: number, provider: string) =>
    request<{ provider: string; zoom: number; tiles: number; fetched: number; ms: number }>(
      `/imagery/warm?lat=${lat}&lon=${lon}&zoom=${zoom}&provider=${provider}`,
    ),
  search: (q: string) =>
    request<{ query: string; source: string; results: PlaceResult[] }>(
      `/imagery/search?q=${encodeURIComponent(q)}`,
    ),

  // --- administrative divisions ---
  geoSearch: (q: string, limit = 8) =>
    request<{ query: string; count: number; results: RegionHit[] }>(
      `/geo/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  geoLocate: (lon: number, lat: number) =>
    request<{ province: RegionHit | null; city: RegionHit | null }>(
      `/geo/locate?lat=${lat}&lon=${lon}`,
    ),

  // --- admin: regions & meteo ---
  adminRegionOverview: (days = 7) =>
    request<RegionOverview>(`/admin/regions/overview?days=${days}`),
  adminRegionSummary: (code: string, days = 7) =>
    request<RegionSummary>(`/admin/regions/summary?code=${code}&days=${days}`),
  adminMeteoStatus: () => request<MeteoStatus>('/admin/meteo/status'),
  adminMeteoFs: (path?: string) =>
    request<FsListing>(`/admin/meteo/fs${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  adminMeteoScan: (path: string, ingest = true) =>
    request<{ found: number; files: string[]; ingested: IngestReport | null }>('/admin/meteo/scan', {
      method: 'POST',
      body: JSON.stringify({ path, ingest, copy: true }),
    }),
  adminMeteoRebuild: () => request<IngestReport>('/admin/meteo/rebuild', { method: 'POST' }),
  adminMeteoUpload: async (files: FileList | File[]) => {
    const form = new FormData()
    Array.from(files).forEach((file) => form.append('files', file))
    return request<{ saved: string[]; ingested: IngestReport | null }>(
      '/admin/meteo/upload?ingest=true',
      { method: 'POST', body: form },
    )
  },

  // --- sync ---
  sync: (ops: unknown[]) =>
    request<{ applied: string[]; skipped: string[]; conflicts: unknown[]; fields: Field[] }>(
      '/sync',
      { method: 'POST', body: JSON.stringify({ ops }) },
    ),

  // --- admin ---
  adminUsers: () => request<User[]>('/admin/users'),
  adminFields: () => request<Field[]>('/admin/fields'),
  adminStats: (days = 7) => request<AdminStats>(`/admin/stats?days=${days}`),
  adminLogs: () => request<HistoryLog[]>('/admin/logs'),
  adminParams: (scope = 'global') =>
    request<ParamScope>(`/admin/params?scope=${encodeURIComponent(scope)}`),
  adminUpdateParams: (scope: string, values: Record<string, number | null>) =>
    request<ParamScope>('/admin/params', {
      method: 'PATCH',
      body: JSON.stringify({ scope, values }),
    }),
}

export function tileUrl(provider: string, z: number, x: number, y: number) {
  return `${BASE}/imagery/tiles/${provider}/${z}/${x}/${y}`
}

export function absoluteUrl(path: string) {
  return `${BASE}${path}`
}
