import { create } from 'zustand'

export type SheetSnap = 'peek' | 'half' | 'full'
export type Provider = 'esri' | 'amap' | 'sentinel2' | 'tianditu'

interface UIState {
  theme: 'dark' | 'light'
  provider: Provider
  railOpen: boolean
  sheet: SheetSnap
  detailOpen: boolean
  toast: { id: number; text: string; tone: 'info' | 'error' | 'success' } | null
  busyLabel: string | null

  toggleTheme: () => void
  setProvider: (provider: Provider) => void
  setRailOpen: (open: boolean) => void
  setSheet: (snap: SheetSnap) => void
  setDetailOpen: (open: boolean) => void
  notify: (text: string, tone?: 'info' | 'error' | 'success') => void
  setBusy: (label: string | null) => void
}

const storedTheme = (localStorage.getItem('hydrocs.theme') as 'dark' | 'light' | null) ?? 'dark'
const storedProvider = (localStorage.getItem('hydrocs.provider') as Provider | null) ?? 'esri'

function applyTheme(theme: 'dark' | 'light') {
  document.documentElement.classList.toggle('hc-light', theme === 'light')
  document.documentElement.classList.toggle('hc-dark', theme === 'dark')
  const meta = document.querySelector('meta[name="theme-color"]')
  meta?.setAttribute('content', theme === 'light' ? '#eef1f4' : '#0a0e13')
}

applyTheme(storedTheme)

let toastTimer: number | undefined

export const useUI = create<UIState>((set) => ({
  theme: storedTheme,
  provider: storedProvider,
  railOpen: false,
  sheet: 'peek',
  detailOpen: false,
  toast: null,
  busyLabel: null,

  toggleTheme: () =>
    set((state) => {
      const theme = state.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('hydrocs.theme', theme)
      applyTheme(theme)
      return { theme }
    }),

  setProvider: (provider) => {
    localStorage.setItem('hydrocs.provider', provider)
    set({ provider })
  },

  setRailOpen: (railOpen) => set({ railOpen }),
  setSheet: (sheet) => set({ sheet }),
  setDetailOpen: (detailOpen) => set({ detailOpen }),

  notify: (text, tone = 'info') => {
    const id = Date.now()
    set({ toast: { id, text, tone } })
    window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => set({ toast: null }), 3200)
  },

  setBusy: (busyLabel) => set({ busyLabel }),
}))
