import type { Map as MLMap } from 'maplibre-gl'
import { expandBBox, ringBBox } from '../lib/geo'
import type { Field } from '../types'

export const mapBridge: { map: MLMap | null } = { map: null }

export function flyToBBox(
  bbox: [number, number, number, number],
  options: { padding?: number; duration?: number; maxZoom?: number } = {},
) {
  const map = mapBridge.map
  if (!map) return
  map.fitBounds(
    [
      [bbox[0], bbox[1]],
      [bbox[2], bbox[3]],
    ],
    {
      padding: options.padding ?? 64,
      duration: options.duration ?? 900,
      maxZoom: options.maxZoom ?? 18,
    },
  )
}

export function flyToPoint(lon: number, lat: number, zoom = 17) {
  mapBridge.map?.flyTo({ center: [lon, lat], zoom, duration: 900 })
}

export function flyToField(field: Field) {
  const ring = field.geometry.coordinates[0].map((p) => [p[0], p[1]] as [number, number])
  flyToBBox(expandBBox(ringBBox(ring), 0.35), { padding: 48, maxZoom: 18 })
}

export function currentViewBBox(): [number, number, number, number] | null {
  const map = mapBridge.map
  if (!map) return null
  const bounds = map.getBounds()
  const bbox: [number, number, number, number] = [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ]
  // Cap the recognisable area: beyond ~1.5 km² the model loses detail.
  const widthDeg = bbox[2] - bbox[0]
  const heightDeg = bbox[3] - bbox[1]
  if (widthDeg > 0.02 || heightDeg > 0.02) {
    const cx = (bbox[0] + bbox[2]) / 2
    const cy = (bbox[1] + bbox[3]) / 2
    return [cx - 0.01, cy - 0.01, cx + 0.01, cy + 0.01]
  }
  return bbox
}

export function currentZoom(): number {
  return mapBridge.map?.getZoom() ?? 16
}

export function center(): [number, number] {
  const c = mapBridge.map?.getCenter()
  return c ? [c.lng, c.lat] : [118.7996, 37.7994]
}
