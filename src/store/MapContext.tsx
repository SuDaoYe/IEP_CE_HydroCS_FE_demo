import { createContext, useContext, useState, type ReactNode } from 'react'

export type LayerMode = 'vector' | 'satellite'

interface MapContextType {
  zoom: number
  setZoom: (z: number) => void
  center: [number, number]
  setCenter: (c: [number, number]) => void
  layerMode: LayerMode
  setLayerMode: (m: LayerMode) => void
}

const MapContext = createContext<MapContextType | null>(null)

export function MapProvider({ children }: { children: ReactNode }) {
  const [zoom, setZoom] = useState(5)
  const [center, setCenter] = useState<[number, number]>([35.8617, 104.1954])
  const [layerMode, setLayerMode] = useState<LayerMode>('vector')

  return (
    <MapContext.Provider value={{ zoom, setZoom, center, setCenter, layerMode, setLayerMode }}>
      {children}
    </MapContext.Provider>
  )
}

export function useMap() {
  const ctx = useContext(MapContext)
  if (!ctx) throw new Error('useMap must be used within MapProvider')
  return ctx
}
