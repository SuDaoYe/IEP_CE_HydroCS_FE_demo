import { http, HttpResponse, delay } from 'msw'
import { setupWorker } from 'msw/browser'
import { users, fields, irrigationRecords, weatherStatus } from './mock-data'
import { generateToken } from './auth'
import type { Field } from '../types'

const lag = () => delay(Math.random() * 300 + 100)

export const handlers = [
  // ---- Auth ----
  http.post('/api/auth/login', async ({ request }) => {
    await lag()
    const body = await request.json() as { username: string; password: string }
    const user = users.find(u => u.username === body.username && u.password === body.password)
    if (!user) {
      return HttpResponse.json({ error: '用户名或密码错误' }, { status: 401 })
    }
    const token = generateToken()
    return HttpResponse.json({
      token,
      user: { id: user.id, username: user.username, role: user.role, name: user.name },
    })
  }),

  http.get('/api/auth/me', async ({ request }) => {
    await lag()
    const authHeader = request.headers.get('Authorization')
    if (!authHeader) return HttpResponse.json({ error: '未登录' }, { status: 401 })
    const token = authHeader.replace('Bearer ', '')
    const user = users[0]
    return HttpResponse.json({ id: user.id, username: user.username, role: user.role, name: user.name })
  }),

  // ---- Admin: Users ----
  http.get('/api/admin/users', async () => {
    await lag()
    return HttpResponse.json(users.map(({ password, ...u }) => u))
  }),

  // ---- Admin: Fields ----
  http.get('/api/admin/fields', async () => {
    await lag()
    return HttpResponse.json(fields)
  }),

  http.put('/api/admin/fields/:id', async ({ params, request }) => {
    await lag()
    const body = await request.json() as Partial<Field>
    const idx = fields.findIndex(f => f.id === params.id)
    if (idx === -1) return HttpResponse.json({ error: '田块不存在' }, { status: 404 })
    Object.assign(fields[idx], body)
    return HttpResponse.json(fields[idx])
  }),

  // ---- Admin: Stats ----
  http.get('/api/admin/stats', async () => {
    await lag()
    const boundFields = fields.filter(f => f.ownerId !== null)
    const totalPredicted = irrigationRecords.filter(r => r.date === '2026-06-10').reduce((s, r) => s + r.predicted, 0)
    return HttpResponse.json({
      activeUsers: [...new Set(boundFields.map(f => f.ownerId))].length,
      boundFields: boundFields.length,
      totalFields: fields.length,
      totalPredictedWater: totalPredicted,
      coverageRate: Math.round((boundFields.length / fields.length) * 100),
    })
  }),

  // ---- Admin: Weather ----
  http.get('/api/admin/weather', async () => {
    await lag()
    return HttpResponse.json(weatherStatus)
  }),

  // ---- User: Nearby fields ----
  http.get('/api/fields/nearby', async ({ request }) => {
    await lag()
    const url = new URL(request.url)
    const lat = parseFloat(url.searchParams.get('lat') || '30.26')
    const lng = parseFloat(url.searchParams.get('lng') || '120.17')
    const nearby = fields.map(f => ({
      ...f,
      distance: Math.sqrt(
        Math.pow(f.bounds[0][0] - lat, 2) + Math.pow(f.bounds[0][1] - lng, 2)
      ) * 111000,
    })).sort((a, b) => a.distance - b.distance)
    return HttpResponse.json(nearby)
  }),

  // ---- User: My fields ----
  http.get('/api/my/fields', async ({ request }) => {
    await lag()
    const authHeader = request.headers.get('Authorization') || ''
    return HttpResponse.json(fields.filter(f => f.ownerId !== null))
  }),

  http.post('/api/my/fields/bind', async ({ request }) => {
    await lag()
    const body = await request.json() as { fieldId: string; ownerId: string; crop: string; growthStage: string; plantDate: string }
    const field = fields.find(f => f.id === body.fieldId)
    if (!field) return HttpResponse.json({ error: '田块不存在' }, { status: 404 })
    field.ownerId = body.ownerId
    field.crop = body.crop
    field.growthStage = body.growthStage
    field.plantDate = body.plantDate
    return HttpResponse.json(field)
  }),

  http.put('/api/my/fields/:id', async ({ params, request }) => {
    await lag()
    const body = await request.json() as { crop?: string; growthStage?: string }
    const field = fields.find(f => f.id === params.id)
    if (!field) return HttpResponse.json({ error: '田块不存在' }, { status: 404 })
    if (body.crop) field.crop = body.crop
    if (body.growthStage) field.growthStage = body.growthStage
    return HttpResponse.json(field)
  }),

  // ---- User: Irrigation ----
  http.get('/api/my/fields/:id/irrigation', async ({ params }) => {
    await lag()
    const records = irrigationRecords.filter(r => r.fieldId === params.id)
    return HttpResponse.json(records)
  }),
]

export const worker = setupWorker(...handlers)
