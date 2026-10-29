export type Role = 'admin' | 'farmer'

export interface User {
  id: string
  username: string
  name: string
  phone: string | null
  role: Role
  created_at: string
  field_count?: number | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export type Ring = [number, number][]

export interface PolygonGeometry {
  type: 'Polygon'
  coordinates: Ring[]
}

export interface Field {
  id: string
  owner_id: string
  owner_name: string | null
  name: string
  crop: string | null
  stage_key: string | null
  plant_date: string | null
  note: string | null
  geometry: PolygonGeometry
  area_m2: number
  area_mu: number
  area_ha: number
  source: string
  confidence: number | null
  created_at: string
  updated_at: string
  rev: number
  kc: number | null
  stage_label: string | null
  crop_label: string | null
}

export interface CandidateFeature {
  type: 'Feature'
  geometry: PolygonGeometry
  properties: {
    area_m2: number
    area_mu: number
    area_ha: number
    confidence: number
    source: string
  }
}

export interface SegmentResult {
  backend: string
  error: string | null
  zoom: number
  provider: string
  bbox: [number, number, number, number]
  bbox_requested?: [number, number, number, number]
  image: { width: number; height: number; mpp_x: number; mpp_y: number }
  count: number
  total_area_ha: number
  coverage_pct: number | null
  features: CandidateFeature[]
  cached?: boolean
}

export interface IrrigationDay {
  date: string
  et0_mm: number
  precip_mm?: number | null
  pe_mm: number
  et_grid_mm?: number
  t2m_c?: number | null
  vpd_kpa?: number | null
  et0_min?: number | null
  et0_max?: number | null
  etc_mm: number
  kc: number
  percolation_mm: number
  net_mm: number
  gross_mm: number
  net_volume_m3?: number
  volume_m3: number
  cumulative_m3: number
  source?: string
  extrapolated?: boolean
}

export interface IrrigationPlan {
  window: { start: string; days: number }
  crop: {
    key: string
    label: string
    stage_key: string | null
    stage_label: string
    kc: number
    kc_scale: number
    paddy: boolean
  }
  area: { m2: number; mu: number; ha: number }
  method?: 'era5-pm' | 'etmonitor-inverse'
  params: {
    efficiency: number
    kc_reference: number
    effective_rain_mm_day: number
    effective_rain_ratio?: number
  }
  series: IrrigationDay[]
  aggregates?: {
    weekly: WaterBucket[]
    monthly: WaterBucket[]
    cumulative: {
    days: number
    volume_m3: number
    net_volume_m3?: number
    gross_volume_m3?: number
    avg_daily_m3?: number
    avg_daily_net_m3?: number
  }
  }
  totals: {
    net_mm: number
    gross_mm: number
    rain_mm?: number
    pe_mm?: number
    /** 需要灌溉的水量（净） */
    net_volume_m3?: number
    /** 总水量（毛，计入输水损失） */
    gross_volume_m3?: number
    volume_m3: number
    daily_avg_m3: number
    daily_avg_net_m3?: number
    per_mu_m3: number | null
    per_mu_net_m3?: number | null
  }
  assumptions: string[]
  domain?: { available: boolean; error?: string | null }
  field?: { id: string; name: string; owner_id: string }
}

export interface CropStage {
  key: string
  label: string
  kc: number
}

export interface Crop {
  key: string
  label: string
  paddy: boolean
  percolation_mm_day: number
  stages: CropStage[]
}

export interface ProviderInfo {
  key: string
  label: string
  datum: string
  min_zoom: number
  max_zoom: number
  requires_key: boolean
  enabled: boolean
  note: string
}

export interface PlaceResult {
  name: string
  address?: string
  lon: number
  lat: number
  level: string
  source: string
}

export interface SummaryTotals {
  fields: number
  area_mu: number
  /** 今日总水量（毛） */
  daily_m3: number
  /** 今日需要灌溉的水量（净） */
  daily_net_m3?: number
  week_m3: number
  week_net_m3?: number
  by_date: { date: string; volume_m3: number; net_volume_m3?: number }[]
}

export interface IrrigationSummary {
  start: string
  days: number
  params: Record<string, number>
  totals: SummaryTotals
  fields: {
    field: {
      id: string
      name: string
      area_mu: number
      crop: string | null
      crop_label: string | null
      stage_label: string | null
    }
    series: IrrigationDay[]
    totals: IrrigationPlan['totals']
    crop: IrrigationPlan['crop']
    area: IrrigationPlan['area']
    aggregates?: IrrigationPlan['aggregates']
  }[]
  assumptions: string[]
}

export interface AdminStats {
  users: number
  farmers: number
  fields: number
  fields_with_crop: number
  coverage_pct: number
  total_area_mu: number
  total_area_ha: number
  daily_m3: number
  week_m3: number
  by_date: { date: string; volume_m3: number }[]
  crop_mix: { crop: string; area_mu: number }[]
  segmentation: { backend: string; weights_present: boolean; error: string | null }
  et_grid: { available: boolean; error?: string | null; domain?: Record<string, unknown> }
  era5?: { available: boolean; error?: string | null; domain?: Record<string, unknown> }
}

export interface HistoryLog {
  id: string
  field_id: string
  field_name: string
  user_name?: string
  computed_at: string
  days: number
  totals: { volume_m3?: number; daily_avg_m3?: number; gross_mm?: number }
}

export interface PendingOp {
  op_id: string
  kind: 'field.create' | 'field.update' | 'field.delete'
  entity_id?: string
  payload: Record<string, unknown>
  client_updated_at: string
}

// --- administrative divisions & admin data -------------------------------

export interface RegionHit {
  adcode: string
  name: string
  fullname: string
  level: 'province' | 'city' | 'district' | 'town' | 'village'
  parent: string | null
  lon: number | null
  lat: number | null
  score: number
  has_geometry: boolean
  /** polygon = 有边界可精确落区；district-center = 只到所属区县中心 */
  precision?: 'polygon' | 'district-center'
}

export interface RegionOverviewRow {
  adcode: string
  name: string
  fullname: string
  province: string | null
  fields: number
  users: number
  area_mu: number
  volume_m3: number
}

export interface RegionOverview {
  days: number
  regions: RegionOverviewRow[]
  unmatched: number
  divisions: { available: boolean; error?: string | null }
}

export interface RegionSummary {
  region: RegionHit
  include_children: boolean
  days: number
  totals: {
    fields: number
    users: number
    area_mu: number
    volume_m3: number
    net_volume_m3?: number
    daily_m3: number
    net_mm_avg: number
  }
  users: { user_id: string; name: string; fields: number; area_mu: number; volume_m3: number }[]
  cities: { adcode: string; name: string; fields: number; area_mu: number; volume_m3: number }[]
  fields: {
    id: string
    name: string
    owner_name: string | null
    area_mu: number
    crop_label: string | null
    city: string | null
    volume_m3: number
  }[]
  crop_mix: { crop: string; area_mu: number }[]
  by_date: { date: string; volume_m3: number }[]
  assumptions: string[]
  generated_at: string
}

export interface IngestReport {
  years_ingested: number[]
  skipped: string[]
  warnings: string[]
  dates_added: number
  dates_replaced: number
  total_dates: number
  coverage: string
}

export interface MeteoStatus {
  inbox: string
  files: number
  years: Record<string, string[]>
  warnings: string[]
  report: IngestReport | null
  cube: { available: boolean; error?: string | null; domain?: Record<string, unknown> }
  target: string
  divisions?: { available: boolean; error?: string | null }
}

export interface FsEntry {
  name: string
  path: string
  type: 'dir' | 'nc'
  size: number | null
}

export interface FsListing {
  path: string
  exists: boolean
  entries: FsEntry[]
  parents: { name: string; path: string }[]
  inbox?: string
  nc_count?: number
}


export interface WaterBucket {
  label: string
  start: string
  end: string
  days: number
  /** 总水量（毛） */
  volume_m3: number
  /** 需要灌溉的水量（净） */
  net_volume_m3?: number
  gross_volume_m3?: number
  net_mm: number
  gross_mm: number
  pe_mm: number
  rain_mm?: number
  avg_daily_m3: number
  avg_daily_net_m3?: number
}


// --- region-scoped model parameters --------------------------------------

export interface ParamSpec {
  key: string
  label: string
  hint: string
  default: number
  min: number
  max: number
  step: number
  group: string
}

export interface ParamScope {
  scope: string
  kind: 'global' | 'province' | 'city'
  adcode: string | null
  region: RegionHit | null
  chain: string[]
  values: Record<string, number>
  sources: Record<string, string>
  overrides: Record<string, Record<string, number>>
  defaults: Record<string, number>
  catalog: ParamSpec[]
  divisions: { available: boolean; error?: string | null }
  scopes: { scope: string; kind: string; adcode: string | null; name: string | null; overrides: number; updated_at: string }[]
}
