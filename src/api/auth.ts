const TOKEN_KEY = 'hydrocs_token'
const USER_KEY = 'hydrocs_user'

export function generateToken(): string {
  return 'mock-jwt-' + Math.random().toString(36).substring(2) + Date.now().toString(36)
}

export function saveAuth(token: string, user: { id: string; username: string; role: string; name: string }) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser(): { id: string; username: string; role: string; name: string } | null {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
