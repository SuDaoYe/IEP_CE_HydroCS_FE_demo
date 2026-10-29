import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { useData } from '../store/data'
import { useUI } from '../store/ui'
import { useWork } from '../store/work'
import { DEFAULT_CENTER, DEFAULT_ZOOM, buildStyle, ensureDataLayers, setGeoJSON, themeColors } from './mapStyle'
import { mapBridge } from './mapBridge'
import type { Field } from '../types'

/** Fields as GeoJSON Features (props carry what the popup needs). */
function fieldCollection(fields: Field[]) {
  return {
    type: 'FeatureCollection' as const,
    features: fields.map((field) => ({
      type: 'Feature' as const,
      id: field.id,
      geometry: field.geometry,
      properties: {
        id: field.id,
        name: field.name,
        crop_label: field.crop_label ?? '未录入作物',
        area_mu: field.area_mu,
      },
    })),
  }
}

function singleCollection(geometry: unknown) {
  return {
    type: 'FeatureCollection' as const,
    features: [{ type: 'Feature' as const, geometry, properties: {} }],
  }
}

export default function MapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])
  const readyRef = useRef(false)
  const [tilesLoading, setTilesLoading] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(DEFAULT_ZOOM)

  const theme = useUI((state) => state.theme)
  const provider = useUI((state) => state.provider)
  const fields = useData((state) => state.fields)
  const selectedId = useData((state) => state.selectedId)
  const select = useData((state) => state.select)

  const mode = useWork((state) => state.mode)
  const draft = useWork((state) => state.draft)
  const candidates = useWork((state) => state.candidates)
  const addVertex = useWork((state) => state.addVertex)
  const moveVertex = useWork((state) => state.moveVertex)
  const adoptCandidate = useWork((state) => state.adoptCandidate)

  // --- init once -------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(provider),
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      maxZoom: 19,
      minZoom: 3,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-left')
    map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false, showAccuracyCircle: false }), 'bottom-right')

    map.on('load', () => {
      ensureDataLayers(map, document.documentElement.classList.contains('hc-dark'))
      readyRef.current = true
      mapBridge.map = map
      ;(window as unknown as { __hcMap?: maplibregl.Map }).__hcMap = map
      syncAll(map)
    })
    map.on('error', (event) => {
      // Surface style/tile failures instead of silently showing a blank canvas.
      console.error('[maplibre]', event.error?.message ?? event)
    })

    mapRef.current = map
    mapBridge.map = map

    return () => {
      map.remove()
      mapRef.current = null
      mapBridge.map = null
      readyRef.current = false
    }
  }, [])

  // --- provider switch -------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    map.setStyle(buildStyle(provider), { diff: false })
    map.once('styledata', () => {
      ensureDataLayers(map, theme === 'dark')
      mapRef.current && syncAll(mapRef.current)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider])

  // --- theme repaint ---------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    const palette = themeColors(theme === 'dark')
    const pairs: [string, string, boolean][] = [
      ['fields-fill', 'fill-color', true],
      ['fields-line', 'line-color', true],
      ['selected-fill', 'fill-color', true],
      ['selected-line', 'line-color', true],
      ['candidates-fill', 'fill-color', true],
      ['candidates-line', 'line-color', true],
      ['draft-fill', 'fill-color', true],
      ['draft-line', 'line-color', true],
    ]
    const values: Record<string, string> = {
      'fields-fill': palette.fieldFill,
      'fields-line': palette.fieldLine,
      'selected-fill': palette.selectedFill,
      'selected-line': palette.selectedLine,
      'candidates-fill': palette.candidateFill,
      'candidates-line': palette.candidateLine,
      'draft-fill': palette.draftFill,
      'draft-line': palette.draftLine,
    }
    for (const [layer, prop] of pairs) {
      if (map.getLayer(layer)) map.setPaintProperty(layer, prop, values[layer])
    }
  }, [theme])

  function syncAll(map: maplibregl.Map) {
    const store = useData.getState()
    setGeoJSON(map, 'fields', fieldCollection(store.fields))
    const selected = store.fields.find((f) => f.id === store.selectedId)
    setGeoJSON(map, 'selected', selected ? singleCollection(selected.geometry) : { type: 'FeatureCollection', features: [] })
  }

  // --- data layers -----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    setGeoJSON(map, 'fields', fieldCollection(fields))
  }, [fields])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const selected = fields.find((f) => f.id === selectedId)
    setGeoJSON(
      map,
      'selected',
      selected ? singleCollection(selected.geometry) : { type: 'FeatureCollection', features: [] },
    )
  }, [selectedId, fields])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    setGeoJSON(map, 'candidates', {
      type: 'FeatureCollection',
      features: candidates.map((feature, index) => ({
        ...feature,
        properties: { ...feature.properties, index },
      })),
    })
  }, [candidates])

  // draft ring: fill only when closed enough to render
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (draft.length < 2) {
      setGeoJSON(map, 'draft', { type: 'FeatureCollection', features: [] })
    } else {
      const closed = [...draft]
      if (draft.length >= 3) closed.push(draft[0])
      setGeoJSON(map, 'draft', {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry:
              draft.length >= 3
                ? { type: 'Polygon', coordinates: [closed] }
                : { type: 'LineString', coordinates: closed },
            properties: {},
          },
        ],
      })
    }
  }, [draft])

  // --- vertex handles --------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    const editable = mode === 'draw' || mode === 'edit' || mode === 'review'
    if (!editable) return

    draft.forEach(([lon, lat], index) => {
      const el = document.createElement('div')
      el.style.width = '24px'
      el.style.height = '24px'
      el.style.display = 'grid'
      el.style.placeItems = 'center'
      el.style.cursor = 'grab'
      const dot = document.createElement('div')
      dot.style.width = '11px'
      dot.style.height = '11px'
      dot.style.borderRadius = '999px'
      dot.style.background = mode === 'draw' ? '#4aa8f0' : '#f5b544'
      dot.style.border = '2px solid rgba(10,14,19,0.9)'
      dot.style.boxShadow = '0 2px 8px rgba(0,0,0,0.5)'
      el.appendChild(dot)

      const marker = new maplibregl.Marker({ element: el, draggable: true, anchor: 'center' })
        .setLngLat([lon, lat])
        .addTo(map)
      marker.on('drag', () => {
        const position = marker.getLngLat()
        moveVertex(index, position.lng, position.lat)
      })
      markersRef.current.push(marker)
    })
  }, [draft, mode, moveVertex])

  // --- interactions ----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const onMapClick = (event: maplibregl.MapMouseEvent) => {
      if (useWork.getState().mode === 'draw') {
        addVertex(event.lngLat.lng, event.lngLat.lat)
      }
    }

    const onFieldClick = (event: maplibregl.MapLayerMouseEvent) => {
      if (useWork.getState().mode !== 'idle') return
      const id = event.features?.[0]?.properties?.id as string | undefined
      if (id) select(id)
    }

    const onCandidateClick = (event: maplibregl.MapLayerMouseEvent) => {
      if (useWork.getState().mode === 'idle' || useWork.getState().mode === 'review') {
        const index = event.features?.[0]?.properties?.index
        if (typeof index === 'number') adoptCandidate(index)
      }
    }

    const enterField = () => {
      map.getCanvas().style.cursor = 'pointer'
    }
    const leaveField = () => {
      map.getCanvas().style.cursor = ''
    }

    map.on('click', onMapClick)
    map.on('click', 'fields-fill', onFieldClick)
    map.on('click', 'candidates-fill', onCandidateClick)
    map.on('mouseenter', 'fields-fill', enterField)
    map.on('mouseleave', 'fields-fill', leaveField)

    return () => {
      map.off('click', onMapClick)
      map.off('click', 'fields-fill', onFieldClick)
      map.off('click', 'candidates-fill', onCandidateClick)
      map.off('mouseenter', 'fields-fill', enterField)
      map.off('mouseleave', 'fields-fill', leaveField)
    }
  }, [addVertex, adoptCandidate, select])

  // Middle-button (wheel) drag pans the map. Needed while drawing, where the
  // left button adds vertices and touch has only two-finger pan.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const canvas = map.getCanvasContainer()
    let last: { x: number; y: number } | null = null

    const onDown = (event: MouseEvent) => {
      if (event.button !== 1) return
      event.preventDefault()
      last = { x: event.clientX, y: event.clientY }
      canvas.style.cursor = 'grabbing'
    }
    const onMove = (event: MouseEvent) => {
      if (!last) return
      event.preventDefault()
      const dx = event.clientX - last.x
      const dy = event.clientY - last.y
      last = { x: event.clientX, y: event.clientY }
      map.panBy([-dx, -dy], { animate: false })
    }
    const onUp = () => {
      if (!last) return
      last = null
      canvas.style.cursor = ''
    }
    const stopAux = (event: Event) => event.preventDefault()

    canvas.addEventListener('mousedown', onDown)
    canvas.addEventListener('auxclick', stopAux)
    window.addEventListener('mousemove', onMove, { passive: false })
    window.addEventListener('mouseup', onUp)
    return () => {
      canvas.removeEventListener('mousedown', onDown)
      canvas.removeEventListener('auxclick', stopAux)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  // Show a chip while imagery is still streaming in — a blank map otherwise
  // looks like a failure rather than "still loading".
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const onLoading = () => setTilesLoading(true)
    const onIdle = () => setTilesLoading(false)
    const onZoom = () => setZoomLevel(map.getZoom())
    map.on('dataloading', onLoading)
    map.on('idle', onIdle)
    map.on('zoomend', onZoom)
    return () => {
      map.off('dataloading', onLoading)
      map.off('idle', onIdle)
      map.off('zoomend', onZoom)
    }
  }, [])

  const drawing = mode === 'draw'

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* MapLibre forces .maplibregl-map to position:relative, so this element
          must carry an explicit height rather than relying on inset-0. */}
      <div ref={containerRef} className="h-full w-full" />
      {tilesLoading && (
        <div className="pointer-events-none absolute inset-x-0 top-2 z-10 flex justify-center">
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--hc-line)] bg-[var(--hc-surface)]/92 px-2.5 py-1 text-[10.5px] text-[var(--hc-muted)] shadow-lg backdrop-blur">
            <span className="hc-pulse inline-block h-1.5 w-1.5 rounded-full bg-[var(--hc-sky)]" />
            影像加载中
          </div>
        </div>
      )}
      {drawing && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-10 flex justify-center">
          <div className="hc-rise rounded-full border border-[var(--hc-line)] bg-[var(--hc-surface)]/95 px-3 py-1.5 text-[11px] text-[var(--hc-muted)] shadow-lg">
            点按加点 · 双指/中键拖动地图 · 至少 3 点后闭合
          </div>
        </div>
      )}
      {!drawing && zoomLevel >= 18.5 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-10 flex justify-center">
          <div className="rounded-full border border-[var(--hc-line)] bg-[var(--hc-surface)]/95 px-2.5 py-1 text-[10.5px] text-[var(--hc-muted)] shadow-lg">
            已超出该处影像原生分辨率，上采样显示
          </div>
        </div>
      )}
    </div>
  )
}
