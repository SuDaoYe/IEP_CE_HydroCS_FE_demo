import { create } from 'zustand'
import type { CandidateFeature, Field, Ring } from '../types'
import { polygonFromRing } from '../lib/geo'
import { useData } from './data'

export type MapMode = 'idle' | 'draw' | 'review' | 'edit'

interface WorkState {
  mode: MapMode
  draft: Ring
  editingId: string | null
  candidates: CandidateFeature[]
  candidateHover: number | null
  segmentMeta: {
    backend: string
    coverage: number | null
    count: number
    totalAreaHa: number
    zoom: number
    mpp: number
    cached: boolean
  } | null
  segmentError: string | null

  startDraw: () => void
  addVertex: (lon: number, lat: number) => void
  undoVertex: () => void
  closeDraft: () => void
  cancel: () => void
  adoptCandidate: (index: number) => void
  startEdit: (field: Field) => void
  moveVertex: (index: number, lon: number, lat: number) => void
  setCandidates: (
    features: CandidateFeature[],
    meta: WorkState['segmentMeta'],
    error?: string | null,
  ) => void
  clearCandidates: () => void
  setHover: (index: number | null) => void
  save: (meta: {
    name: string
    crop: string | null
    stage_key: string | null
    plant_date: string | null
    source?: string
    confidence?: number | null
  }) => Promise<Field | null>
}

export const useWork = create<WorkState>((set, get) => ({
  mode: 'idle',
  draft: [],
  editingId: null,
  candidates: [],
  candidateHover: null,
  segmentMeta: null,
  segmentError: null,

  startDraw: () => set({ mode: 'draw', draft: [], editingId: null }),
  addVertex: (lon, lat) => set((state) => ({ draft: [...state.draft, [lon, lat]] })),
  undoVertex: () => set((state) => ({ draft: state.draft.slice(0, -1) })),
  closeDraft: () => set((state) => (state.draft.length >= 3 ? { mode: 'review' } : state)),

  cancel: () => set({ mode: 'idle', draft: [], editingId: null }),

  adoptCandidate: (index) =>
    set((state) => {
      const feature = state.candidates[index]
      if (!feature) return state
      const ring = feature.geometry.coordinates[0].slice(0, -1) as Ring
      return { mode: 'review', draft: ring, editingId: null }
    }),

  startEdit: (field) =>
    set({
      mode: 'edit',
      editingId: field.id,
      draft: field.geometry.coordinates[0].slice(0, -1) as Ring,
    }),

  moveVertex: (index, lon, lat) =>
    set((state) => {
      const draft = [...state.draft]
      draft[index] = [lon, lat]
      return { draft }
    }),

  setCandidates: (features, meta, error = null) =>
    set({ candidates: features, segmentMeta: meta, segmentError: error }),

  clearCandidates: () => set({ candidates: [], segmentMeta: null, segmentError: null }),
  setHover: (candidateHover) => set({ candidateHover }),

  save: async (meta) => {
    const { mode, draft, editingId } = get()
    if (draft.length < 3) return null
    const geometry = polygonFromRing(draft) as unknown as Field['geometry']
    const store = useData.getState()

    if (mode === 'edit' && editingId) {
      await store.patchField(editingId, {
        geometry,
        name: meta.name,
        crop: meta.crop,
        stage_key: meta.stage_key,
        plant_date: meta.plant_date,
      })
      set({ mode: 'idle', draft: [], editingId: null, candidates: [] })
      return store.fields.find((f) => f.id === editingId) ?? null
    }

    const created = await store.createField({
      name: meta.name,
      geometry,
      crop: meta.crop,
      stage_key: meta.stage_key,
      plant_date: meta.plant_date,
      source: meta.source ?? 'manual',
      confidence: meta.confidence ?? null,
    })
    set({ mode: 'idle', draft: [], candidates: [], editingId: null })
    return created
  },
}))
