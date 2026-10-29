import { create } from 'zustand'
import { api } from '../lib/api'
import type { IrrigationPlan, IrrigationSummary } from '../types'

interface IrrigationState {
  days: number
  summary: IrrigationSummary | null
  summaryLoading: boolean
  plan: IrrigationPlan | null
  planLoading: boolean
  planFor: string | null
  error: string | null

  setDays: (days: number) => void
  loadSummary: (days?: number) => Promise<void>
  loadPlan: (fieldId: string | null, days?: number) => Promise<void>
}

export const useIrrigation = create<IrrigationState>((set, get) => ({
  days: 7,
  summary: null,
  summaryLoading: false,
  plan: null,
  planLoading: false,
  planFor: null,
  error: null,

  setDays: (days) => set({ days }),

  loadSummary: async (days) => {
    const span = days ?? get().days
    set({ summaryLoading: true, error: null })
    try {
      const summary = await api.summary(span)
      set({ summary, summaryLoading: false })
    } catch (error) {
      set({ summaryLoading: false, error: (error as Error).message })
    }
  },

  loadPlan: async (fieldId, days) => {
    if (!fieldId) {
      set({ plan: null, planFor: null })
      return
    }
    const span = days ?? get().days
    set({ planLoading: true, planFor: fieldId, error: null })
    try {
      const plan = await api.irrigation(fieldId, span)
      set({ plan, planLoading: false })
    } catch (error) {
      set({ planLoading: false, plan: null, error: (error as Error).message })
    }
  },
}))
