import { create } from 'zustand'
import { api } from '../lib/api'
import { offline } from '../lib/idb'
import type { Field, PendingOp } from '../types'

interface DataState {
  fields: Field[]
  loading: boolean
  syncing: boolean
  error: string | null
  offline: boolean
  pendingCount: number
  selectedId: string | null

  load: () => Promise<void>
  select: (id: string | null) => void
  refreshPending: () => Promise<void>
  createField: (payload: {
    name: string
    geometry: Field['geometry']
    crop: string | null
    stage_key: string | null
    plant_date: string | null
    source?: string
    confidence?: number | null
  }) => Promise<Field>
  patchField: (id: string, payload: Record<string, unknown>) => Promise<void>
  removeField: (id: string) => Promise<void>
  sync: () => Promise<{ applied: number; conflicts: number }>
}

function tempId() {
  return `local_${Math.random().toString(36).slice(2, 10)}`
}

function opId() {
  return `op_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export const useData = create<DataState>((set, get) => ({
  fields: [],
  loading: false,
  syncing: false,
  error: null,
  offline: !navigator.onLine,
  pendingCount: 0,
  selectedId: null,

  load: async () => {
    set({ loading: true, error: null })
    try {
      const fields = await api.listFields()
      await offline.putFields(fields)
      set({ fields, loading: false, offline: false })
    } catch (error) {
      const cached = await offline.allFields()
      set({
        fields: cached,
        loading: false,
        offline: true,
        error: cached.length ? null : (error as Error).message,
      })
    }
    await get().refreshPending()
  },

  select: (id) => set({ selectedId: id }),

  refreshPending: async () => {
    const ops = await offline.pending()
    set({ pendingCount: ops.length })
  },

  createField: async (payload) => {
    const now = new Date().toISOString()
    const optimistic: Field = {
      id: tempId(),
      owner_id: 'local',
      owner_name: null,
      name: payload.name,
      crop: payload.crop,
      stage_key: payload.stage_key,
      plant_date: payload.plant_date,
      note: null,
      geometry: payload.geometry,
      area_m2: 0,
      area_mu: 0,
      area_ha: 0,
      source: payload.source ?? 'manual',
      confidence: payload.confidence ?? null,
      created_at: now,
      updated_at: now,
      rev: 1,
      kc: null,
      stage_label: null,
      crop_label: null,
    }

    try {
      const created = await api.createField({
        name: payload.name,
        geometry: payload.geometry,
        crop: payload.crop,
        stage_key: payload.stage_key,
        plant_date: payload.plant_date,
        source: payload.source ?? 'manual',
        confidence: payload.confidence ?? null,
      })
      await offline.putField(created)
      set((state) => ({ fields: [created, ...state.fields], selectedId: created.id }))
      return created
    } catch (error) {
      const op: PendingOp = {
        op_id: opId(),
        kind: 'field.create',
        payload: {
          name: payload.name,
          geometry: payload.geometry,
          crop: payload.crop,
          stage_key: payload.stage_key,
          plant_date: payload.plant_date,
          source: payload.source ?? 'manual',
        },
        client_updated_at: now,
      }
      await offline.enqueue(op)
      set((state) => ({ fields: [optimistic, ...state.fields], selectedId: optimistic.id, offline: true }))
      await get().refreshPending()
      throw error
    }
  },

  patchField: async (id, payload) => {
    try {
      const updated = await api.updateField(id, payload)
      await offline.putField(updated)
      set((state) => ({
        fields: state.fields.map((field) => (field.id === id ? updated : field)),
      }))
    } catch (error) {
      const op: PendingOp = {
        op_id: opId(),
        kind: 'field.update',
        entity_id: id,
        payload,
        client_updated_at: new Date().toISOString(),
      }
      await offline.enqueue(op)
      await get().refreshPending()
      throw error
    }
  },

  removeField: async (id) => {
    try {
      await api.deleteField(id)
    } catch {
      await offline.enqueue({
        op_id: opId(),
        kind: 'field.delete',
        entity_id: id,
        payload: {},
        client_updated_at: new Date().toISOString(),
      })
    }
    await offline.dropField(id)
    set((state) => ({
      fields: state.fields.filter((field) => field.id !== id),
      selectedId: state.selectedId === id ? null : state.selectedId,
    }))
    await get().refreshPending()
  },

  sync: async () => {
    const ops = await offline.pending()
    if (!ops.length) return { applied: 0, conflicts: 0 }
    set({ syncing: true })
    try {
      const result = await api.sync(ops)
      const done = [...result.applied, ...result.skipped]
      await offline.removeOps(done)
      const fields = result.fields
      await offline.putFields(fields)
      set({
        fields,
        syncing: false,
        offline: false,
        pendingCount: ops.length - done.length,
      })
      return { applied: result.applied.length, conflicts: result.conflicts.length }
    } catch (error) {
      set({ syncing: false, error: (error as Error).message })
      throw error
    }
  },
}))

window.addEventListener('online', () => {
  useData.setState({ offline: false })
  void useData.getState().sync()
})
window.addEventListener('offline', () => useData.setState({ offline: true }))
