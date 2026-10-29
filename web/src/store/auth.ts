import { create } from 'zustand'
import { ApiError, api, setTokenProvider } from '../lib/api'
import type { User } from '../types'

const TOKEN_KEY = 'hydrocs.token'
const USER_KEY = 'hydrocs.user'

interface AuthState {
  token: string | null
  user: User | null
  ready: boolean
  loading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  bootstrap: () => void
  refresh: () => Promise<void>
}

function readStored(): { token: string | null; user: User | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const raw = localStorage.getItem(USER_KEY)
    return { token, user: raw ? (JSON.parse(raw) as User) : null }
  } catch {
    return { token: null, user: null }
  }
}

const stored = readStored()
setTokenProvider(() => localStorage.getItem(TOKEN_KEY))

export const useAuth = create<AuthState>((set, get) => ({
  token: stored.token,
  user: stored.user,
  ready: false,
  loading: false,
  error: null,

  bootstrap: () => {
    set({ ready: true })
    if (get().token) void get().refresh()
  },

  login: async (username, password) => {
    set({ loading: true, error: null })
    try {
      const payload = await api.login(username, password)
      localStorage.setItem(TOKEN_KEY, payload.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(payload.user))
      set({ token: payload.access_token, user: payload.user, loading: false, ready: true })
    } catch (error) {
      set({ loading: false, error: (error as Error).message })
      throw error
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null })
  },

  refresh: async () => {
    if (!get().token) return
    try {
      const user = await api.me()
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      set({ user })
    } catch (error) {
      // Only an auth failure invalidates the session. A network failure (offline)
      // must keep the stored session so the app stays usable without a connection.
      const status = error instanceof ApiError ? error.status : 0
      if (status === 401 || status === 403) {
        get().logout()
      }
    }
  },
}))
