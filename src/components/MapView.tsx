import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../store/MapContext'

const ESRI_SATELLITE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const AMAP_VECTOR = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

interface Props {
  fields?: any[]
  selectedFieldId?: string
  onFieldClick?: (field: any) => void
}

export default function MapView({ fields = [], selectedFieldId, onFieldClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const [searchText, setSearchText] = useState('')
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

  // Search handler
  const handleSearch = async () => {
    if (!searchText.trim() || !mapRef.current) return
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchText)}&limit=1`
      )
      const data = await res.json()
      if (data[0]) {
        mapRef.current.setView([parseFloat(data[0].lat), parseFloat(data[0].lon)], 14)
      }
    } catch {
      mapRef.current.setView([30.25, 120.17], 14)
    }
  }

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

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex gap-2">
        <input
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="搜索地点..."
          className="w-60 px-3 py-1.5 text-xs bg-[#131820] border border-[#1e2430] rounded-md text-[#9ca3af] outline-none focus:border-[#818cf8]"
        />
        <button onClick={handleSearch}
          className="px-3 py-1.5 text-xs bg-[#131820] border border-[#1e2430] rounded-md text-[#9ca3af] hover:text-[#c8ccd0]">
          搜索
        </button>
      </div>
    </div>
  )
}
