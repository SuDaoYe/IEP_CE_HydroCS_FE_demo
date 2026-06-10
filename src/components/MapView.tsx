import { useEffect, useRef, useState, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../store/MapContext'
import { searchLocations } from '../api/geocode'
import type { GeoResult } from '../api/geocode'

const ESRI_SATELLITE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const AMAP_VECTOR = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

interface Props {
  fields?: any[]
  selectedFieldId?: string
  onFieldClick?: (field: any) => void
  focusLocation?: { lat: number; lng: number; zoom?: number } | null
}

const HISTORY_KEY = 'hydrocs-search-history'
const MAX_HISTORY = 8

function loadHistory(): GeoResult[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveHistory(items: GeoResult[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)))
}

export default function MapView({ fields = [], selectedFieldId, onFieldClick, focusLocation }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const [searchText, setSearchText] = useState('')
  const [searchResults, setSearchResults] = useState<GeoResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const [history, setHistory] = useState<GeoResult[]>(loadHistory)
  const searchMarkerRef = useRef<L.Marker | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const vectorLayerRef = useRef<L.TileLayer | null>(null)
  const satelliteLayerRef = useRef<L.TileLayer | null>(null)
  const geoLayerRef = useRef<L.GeoJSON | null>(null)
  const { setZoom, setCenter, setLayerMode } = useMap()

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: [35.8617, 104.1954],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
    })

    vectorLayerRef.current = L.tileLayer(AMAP_VECTOR, {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 18,
      minZoom: 3,
    }).addTo(map)

    satelliteLayerRef.current = L.tileLayer(ESRI_SATELLITE, {
      maxZoom: 20,
      minZoom: 3,
    })

    map.on('zoomend', () => {
      const z = map.getZoom()
      setZoom(z)
      if (z >= 10) {
        if (map.hasLayer(vectorLayerRef.current!)) {
          map.removeLayer(vectorLayerRef.current!)
          map.addLayer(satelliteLayerRef.current!)
          setLayerMode('satellite')
        }
      } else {
        if (map.hasLayer(satelliteLayerRef.current!)) {
          map.removeLayer(satelliteLayerRef.current!)
          map.addLayer(vectorLayerRef.current!)
          setLayerMode('vector')
        }
      }
    })

    map.on('moveend', () => {
      const c = map.getCenter()
      setCenter([c.lat, c.lng])
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Click outside to close dropdown
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Place a marker at the searched location
  const placeMarker = useCallback((lat: number, lng: number) => {
    if (!mapRef.current) return
    if (searchMarkerRef.current) {
      searchMarkerRef.current.remove()
    }
    const icon = L.divIcon({
      className: '',
      html: `<svg width="32" height="40" viewBox="0 0 32 40"><path d="M16 0C9.37 0 4 5.37 4 12c0 9 12 28 12 28s12-19 12-28C28 5.37 22.63 0 16 0z" fill="#818cf8"/><circle cx="16" cy="12" r="6" fill="white"/></svg>`,
      iconSize: [32, 40],
      iconAnchor: [16, 40],
    })
    const marker = L.marker([lat, lng], { icon }).addTo(mapRef.current)
    marker.bindTooltip(`${lat.toFixed(4)}, ${lng.toFixed(4)}`, { direction: 'top', offset: [0, -36] })
    searchMarkerRef.current = marker
  }, [])

  // Local search (no network dependency)
  const doSearch = useCallback((query: string) => {
    if (!query.trim()) return

    setIsSearching(true)
    setSearchError('')
    setSearchResults([])

    // Small delay so the loading spinner is visible for UX
    setTimeout(() => {
      const results = searchLocations(query, 5)
      setIsSearching(false)

      if (results.length > 0) {
        setSearchResults(results)
        setShowDropdown(true)
      } else {
        setSearchError('未找到匹配地点，请尝试其他关键词')
        setShowDropdown(true)
      }
    }, 150)
  }, [])

  const selectResult = useCallback((result: GeoResult) => {
    if (!mapRef.current) return
    mapRef.current.setView([result.lat, result.lng], 14, { animate: true, duration: 0.8 })
    placeMarker(result.lat, result.lng)
    setSearchText('')
    setShowDropdown(false)

    const newHistory = [result, ...history.filter(h => h.displayName !== result.displayName)]
    setHistory(newHistory)
    saveHistory(newHistory)
  }, [history, placeMarker])

  const handleInputChange = (value: string) => {
    setSearchText(value)
    if (value.trim().length >= 2) {
      doSearch(value)
    } else {
      setSearchResults([])
      setSearchError('')
      setShowDropdown(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchText.trim()) {
      doSearch(searchText)
    }
  }

  const clearHistory = () => {
    setHistory([])
    localStorage.removeItem(HISTORY_KEY)
  }

  // Fly to focus location
  useEffect(() => {
    if (focusLocation && mapRef.current) {
      mapRef.current.setView([focusLocation.lat, focusLocation.lng], focusLocation.zoom || 15, {
        animate: true,
        duration: 1,
      })
      placeMarker(focusLocation.lat, focusLocation.lng)
    }
  }, [focusLocation, placeMarker])

  // Field overlay
  useEffect(() => {
    if (!mapRef.current || fields.length === 0) return

    if (geoLayerRef.current) {
      mapRef.current.removeLayer(geoLayerRef.current)
    }

    const geoLayer = L.geoJSON(
      {
        type: 'FeatureCollection',
        features: fields.map((f: any) => ({
          type: 'Feature' as const,
          properties: { id: f.id, name: f.name, crop: f.crop, ownerId: f.ownerId },
          geometry: {
            type: 'Polygon',
            coordinates: [[...f.bounds.map((b: [number, number]) => [b[1], b[0]]), [f.bounds[0][1], f.bounds[0][0]]]],
          },
        })),
      } as any,
      {
        style: (feature) => {
          const isSelected = feature?.properties.id === selectedFieldId
          const hasOwner = !!feature?.properties.ownerId
          return {
            fillColor: isSelected ? '#818cf8' : hasOwner ? '#fbbf24' : '#4ade80',
            fillOpacity: 0.3,
            color: isSelected ? '#818cf8' : hasOwner ? '#fbbf24' : '#4ade80',
            weight: isSelected ? 3 : 1,
          }
        },
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(feature.properties.name + (feature.properties.crop ? ` · ${feature.properties.crop}` : ''))
          layer.on('click', () => {
            const field = fields.find((f: any) => f.id === feature.properties.id)
            if (field && onFieldClick) onFieldClick(field)
          })
        },
      }
    ).addTo(mapRef.current)

    geoLayerRef.current = geoLayer

    return () => {
      if (mapRef.current && geoLayerRef.current) {
        mapRef.current.removeLayer(geoLayerRef.current)
        geoLayerRef.current = null
      }
    }
  }, [fields, selectedFieldId, onFieldClick])

  const showDropdownContent = showDropdown && (searchResults.length > 0 || isSearching || searchError || (!searchText.trim() && history.length > 0))

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Search bar + dropdown */}
      <div ref={dropdownRef} className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex flex-col" style={{ width: 360 }}>
        <div className="flex gap-2">
          <input
            value={searchText}
            onChange={e => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => { if (searchResults.length > 0 || history.length > 0) setShowDropdown(true) }}
            placeholder="搜索地点..."
            className="flex-1 px-3 py-1.5 text-xs bg-[var(--bg-panel)] border border-[var(--border)] rounded-md text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent)]"
          />
          <button
            onClick={() => searchText.trim() && doSearch(searchText)}
            disabled={isSearching}
            className="px-3 py-1.5 text-xs bg-[var(--bg-panel)] border border-[var(--border)] rounded-md text-[var(--text-body)] hover:text-[var(--text-primary)] disabled:opacity-50 shrink-0"
          >
            {isSearching ? '搜索中...' : '搜索'}
          </button>
        </div>

        {/* Dropdown */}
        {showDropdownContent && (
          <div className="mt-1 bg-[var(--bg-panel)] border border-[var(--border)] rounded-md shadow-lg overflow-hidden max-h-80 overflow-y-auto">
            {isSearching && (
              <div className="px-3 py-2 text-xs text-[var(--text-muted)] flex items-center gap-2">
                <span className="inline-block w-3 h-3 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                搜索中...
              </div>
            )}

            {searchError && !isSearching && (
              <div className="px-3 py-2 text-xs text-[var(--warning)]">{searchError}</div>
            )}

            {!isSearching && !searchError && searchResults.length > 0 && (
              <div>
                <div className="px-3 py-1 text-[9px] text-[var(--text-muted)] uppercase tracking-wider">搜索结果</div>
                {searchResults.map((r, i) => (
                  <button
                    key={i}
                    onClick={() => selectResult(r)}
                    className="w-full text-left px-3 py-2 text-xs text-[var(--text-body)] hover:bg-[var(--accent-bg)] hover:text-[var(--text-primary)] border-b border-[var(--border)] last:border-b-0 transition-colors"
                  >
                    <div className="truncate">{r.displayName}</div>
                    <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{r.lat.toFixed(4)}, {r.lng.toFixed(4)}</div>
                  </button>
                ))}
              </div>
            )}

            {/* Search history */}
            {!isSearching && !searchError && searchResults.length === 0 && history.length > 0 && (
              <div>
                <div className="px-3 py-1 flex justify-between items-center">
                  <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider">搜索历史</span>
                  <button onClick={clearHistory} className="text-[9px] text-[var(--text-muted)] hover:text-[var(--text-body)]">清除</button>
                </div>
                {history.map((r, i) => (
                  <button
                    key={i}
                    onClick={() => selectResult(r)}
                    className="w-full text-left px-3 py-2 text-xs text-[var(--text-body)] hover:bg-[var(--accent-bg)] hover:text-[var(--text-primary)] border-b border-[var(--border)] last:border-b-0 transition-colors"
                  >
                    <div className="truncate">{r.displayName}</div>
                    <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{r.lat.toFixed(4)}, {r.lng.toFixed(4)}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
