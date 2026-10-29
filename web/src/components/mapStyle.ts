import type { GeoJSONSource, GeoJSONSourceSpecification, Map as MLMap, StyleSpecification } from 'maplibre-gl'
import { absoluteUrl } from '../lib/api'

export const DEFAULT_CENTER: [number, number] = [118.7996, 37.7994]
export const DEFAULT_ZOOM = 16

export const PROVIDER_MAX_ZOOM: Record<string, number> = {
  esri: 19,
  amap: 18,
  sentinel2: 15,
  tianditu: 18,
}

export function buildStyle(provider: string): StyleSpecification {
  const maxzoom = PROVIDER_MAX_ZOOM[provider] ?? 18
  return {
    version: 8,
    sources: {
      imagery: {
        type: 'raster',
        tiles: [absoluteUrl(`/imagery/tiles/${provider}/{z}/{x}/{y}`)],
        tileSize: 256,
        minzoom: 2,
        maxzoom,
        attribution: '',
      },
    },
    layers: [
      { id: 'canvas', type: 'background', paint: { 'background-color': '#0a0e13' } },
      {
        id: 'imagery',
        type: 'raster',
        source: 'imagery',
        paint: { 'raster-opacity': 1, 'raster-fade-duration': 180 },
      },
    ],
  }
}

export const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] }

export interface LayerColors {
  fieldFill: string
  fieldLine: string
  selectedFill: string
  selectedLine: string
  candidateFill: string
  candidateLine: string
  draftFill: string
  draftLine: string
}

export function themeColors(dark: boolean): LayerColors {
  return dark
    ? {
        fieldFill: 'rgba(53, 211, 153, 0.24)',
        fieldLine: 'rgba(53, 211, 153, 0.95)',
        selectedFill: 'rgba(74, 168, 240, 0.32)',
        selectedLine: 'rgba(74, 168, 240, 1)',
        candidateFill: 'rgba(245, 181, 68, 0.3)',
        candidateLine: 'rgba(245, 181, 68, 0.98)',
        draftFill: 'rgba(74, 168, 240, 0.34)',
        draftLine: 'rgba(74, 168, 240, 1)',
      }
    : {
        fieldFill: 'rgba(18, 160, 111, 0.26)',
        fieldLine: 'rgba(12, 112, 78, 1)',
        selectedFill: 'rgba(28, 127, 209, 0.3)',
        selectedLine: 'rgba(20, 100, 170, 1)',
        candidateFill: 'rgba(185, 118, 8, 0.28)',
        candidateLine: 'rgba(150, 92, 4, 1)',
        draftFill: 'rgba(28, 127, 209, 0.32)',
        draftLine: 'rgba(20, 100, 170, 1)',
      }
}

/** Adds (once) every data layer the app draws above the imagery. */
export function ensureDataLayers(map: MLMap, dark: boolean) {
  const palette = themeColors(dark)
  const sources: [string, GeoJSONSourceSpecification][] = [
    ['candidates', { type: 'geojson', data: EMPTY_FC }],
    ['fields', { type: 'geojson', data: EMPTY_FC }],
    ['selected', { type: 'geojson', data: EMPTY_FC }],
    ['draft', { type: 'geojson', data: EMPTY_FC }],
  ]
  for (const [id, spec] of sources) {
    if (!map.getSource(id)) map.addSource(id, spec)
  }

  const addFill = (id: string, source: string, color: string) => {
    if (map.getLayer(`${id}-fill`)) return
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source,
      paint: { 'fill-color': color, 'fill-opacity': 1 },
    })
  }
  const addLine = (
    id: string,
    source: string,
    color: string,
    width: number,
    dash?: number[],
    layerId: string = `${id}-line`,
  ) => {
    if (map.getLayer(layerId)) return
    map.addLayer({
      id: layerId,
      type: 'line',
      source,
      paint: {
        'line-color': color,
        'line-width': width,
        ...(dash ? { 'line-dasharray': dash } : {}),
      },
      layout: { 'line-join': 'round', 'line-cap': 'round' },
    })
  }

  // Dark halo under each outline keeps parcels readable over bright crops.
  addLine('fields', 'fields', 'rgba(6, 12, 10, 0.55)', 4.2, undefined, 'fields-halo')
  addLine('fields', 'fields', palette.fieldLine, 2.0)
  addFill('fields', 'fields', palette.fieldFill)

  addLine('candidates', 'candidates', 'rgba(10, 8, 2, 0.5)', 3.6, undefined, 'candidates-halo')
  addLine('candidates', 'candidates', palette.candidateLine, 1.8, [2, 1.4])
  addFill('candidates', 'candidates', palette.candidateFill)

  addLine('selected', 'selected', 'rgba(2, 8, 14, 0.6)', 6, undefined, 'selected-halo')
  addLine('selected', 'selected', palette.selectedLine, 2.8)
  addFill('selected', 'selected', palette.selectedFill)

  addLine('draft', 'draft', 'rgba(2, 8, 14, 0.55)', 5, undefined, 'draft-halo')
  addLine('draft', 'draft', palette.draftLine, 2.2, [1.4, 1])
  addFill('draft', 'draft', palette.draftFill)
}

export function setGeoJSON(map: MLMap, id: string, data: unknown) {
  const source = map.getSource(id) as GeoJSONSource | undefined
  source?.setData(data as never)
}
