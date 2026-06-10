import { http, HttpResponse } from 'msw'
import { setupWorker } from 'msw/browser'

export const handlers = [
  http.post('/api/auth/login', () => {
    return HttpResponse.json({ token: 'mock-token', role: 'admin' })
  }),
]

export const worker = setupWorker(...handlers)
