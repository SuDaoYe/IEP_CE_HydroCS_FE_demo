/** Geometry helpers mirroring the server so the UI can preview areas offline. */

export type Ring = [number, number][]

const EARTH_RADIUS = 6371008.8
const WGS84_A = 6378137.0
const WGS84_F = 1 / 298.257223563
const WGS84_E2 = WGS84_F * (2 - WGS84_F)

export function geodesicArea(ring: Ring): number {
  if (ring.length < 3) return 0
  let total = 0
  for (let i = 0; i < ring.length; i += 1) {
    const [lon1, lat1] = ring[i]
    const [lon2, lat2] = ring[(i + 1) % ring.length]
    const rad = (v: number) => (v * Math.PI) / 180
    total +=
      rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)))
  }
  let area = (Math.abs(total) * EARTH_RADIUS * EARTH_RADIUS) / 2
  const latMean = ring.reduce((sum, p) => sum + p[1], 0) / ring.length
  const phi = (latMean * Math.PI) / 180
  const w = Math.sqrt(1 - WGS84_E2 * Math.sin(phi) ** 2)
  const radius = (WGS84_A * (1 - WGS84_E2)) / w ** 3
  area *= (radius / EARTH_RADIUS) ** 2
  return area
}

export function centroid(ring: Ring): [number, number] {
  if (!ring.length) return [0, 0]
  const lon = ring.reduce((sum, p) => sum + p[0], 0) / ring.length
  const lat = ring.reduce((sum, p) => sum + p[1], 0) / ring.length
  return [lon, lat]
}

export function ringBBox(ring: Ring): [number, number, number, number] {
  const lons = ring.map((p) => p[0])
  const lats = ring.map((p) => p[1])
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)]
}

export function expandBBox(
  bbox: [number, number, number, number],
  factor = 0.15,
): [number, number, number, number] {
  const [minLon, minLat, maxLon, maxLat] = bbox
  const dx = (maxLon - minLon) * factor
  const dy = (maxLat - minLat) * factor
  return [minLon - dx, minLat - dy, maxLon + dx, maxLat + dy]
}

export function geometryToRings(geometry: { coordinates: number[][][] } | null | undefined): Ring[] {
  if (!geometry || !geometry.coordinates) return []
  return geometry.coordinates.map((ring) => ring.slice(0, -1).map((p) => [p[0], p[1]] as [number, number]))
}

export function polygonFromRing(ring: Ring) {
  const closed = [...ring]
  if (closed[0][0] !== closed[closed.length - 1][0] || closed[0][1] !== closed[closed.length - 1][1]) {
    closed.push(closed[0])
  }
  return { type: 'Polygon' as const, coordinates: [closed] }
}

/** 1 m² = 0.0015 亩; 1 亩 = 666.67 m² */
export function m2ToMu(m2: number): number {
  return m2 * 0.0015
}

export function distanceMeters(a: [number, number], b: [number, number]): number {
  const rad = (v: number) => (v * Math.PI) / 180
  const dLat = rad(b[1] - a[1])
  const dLon = rad(b[0] - a[0])
  const lat1 = rad(a[1])
  const lat2 = rad(b[1])
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS * Math.asin(Math.min(1, Math.sqrt(h)))
}
