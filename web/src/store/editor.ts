import { create } from 'zustand'
import { useData } from './data'
import { useIrrigation } from './irrigation'
import { useUI } from './ui'
import { useWork } from './work'
import type { Crop, Field } from '../types'

interface EditorState {
  name: string
  crop: string
  stage: string
  plantDate: string
  saving: boolean
  crops: Crop[]

  setName: (value: string) => void
  setCrop: (value: string) => void
  setStage: (value: string) => void
  setPlantDate: (value: string) => void
  setCrops: (crops: Crop[]) => void
  hydrate: (field: Field | null, fallbackIndex: number) => void
  reset: () => void
  submit: () => Promise<void>
}

export const useEditor = create<EditorState>((set, get) => ({
  name: '',
  crop: '',
  stage: '',
  plantDate: '',
  saving: false,
  crops: [],

  setName: (name) => set({ name }),
  setCrop: (crop) => set({ crop }),
  setStage: (stage) => set({ stage }),
  setPlantDate: (plantDate) => set({ plantDate }),
  setCrops: (crops) => set({ crops }),

  hydrate: (field, fallbackIndex) =>
    set({
      name: field?.name ?? `新田块 ${fallbackIndex}`,
      crop: field?.crop ?? '',
      stage: field?.stage_key ?? '',
      plantDate: field?.plant_date ?? '',
    }),

  reset: () => set({ name: '', crop: '', stage: '', plantDate: '', saving: false }),

  submit: async () => {
    const state = get()
    const work = useWork.getState()
    if (work.draft.length < 3) {
      useUI.getState().notify('至少需要 3 个顶点才能保存', 'error')
      return
    }
    set({ saving: true })
    try {
      const editing = work.editingId
        ? useData.getState().fields.find((field) => field.id === work.editingId) ?? null
        : null
      const saved = await work.save({
        name: state.name.trim() || '未命名田块',
        crop: state.crop || null,
        stage_key: state.stage || null,
        plant_date: state.plantDate || null,
        source: editing ? undefined : work.mode === 'review' ? 'segment+edited' : 'manual',
        confidence: editing?.confidence ?? null,
      })
      useUI.getState().notify(editing ? '形状已更新' : '田块已保存', 'success')
      if (saved) {
        useData.getState().select(saved.id)
        void useIrrigation.getState().loadPlan(saved.id)
      }
    } catch (error) {
      useUI.getState().notify((error as Error).message, 'error')
    } finally {
      set({ saving: false })
    }
  },
}))
