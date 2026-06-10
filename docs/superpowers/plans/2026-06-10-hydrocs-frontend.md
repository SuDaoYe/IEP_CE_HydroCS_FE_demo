# HydroCS 智能灌溉前端 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建智能灌溉管理 Web 前端，包含管理员端和用户端，地图为中心的三栏布局，Mock API 数据模拟。

**Architecture:** React + TypeScript + Vite 单页应用。MSW 在 Service Worker 层拦截请求返回模拟数据。NextUI 提供组件和主题系统。Leaflet 处理地图，react-leaflet 做 React 封装。AuthContext + MapContext 两个全局状态，页面级数据各自管理。

**Tech Stack:** React 18, TypeScript, Vite, NextUI (HeroUI), Tailwind CSS, Leaflet + react-leaflet, MSW, React Router v6

---

### Task 1: 项目脚手架

**Files:**
- Create: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `tailwind.config.ts`, `postcss.config.js`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/vite-env.d.ts`, `src/index.css`, `public/mockServiceWorker.js`

- [ ] **Step 1: 创建 Vite + React + TypeScript 项目**

Run:
```bash
cd "C:/Users/win11/Desktop/大创/土木"
npm create vite@latest . -- --template react-ts
```

Expected: 在当前目录生成 Vite 项目文件。如果目录非空提示冲突，加 `--force` 或手动删除冲突文件后重试。

- [ ] **Step 2: 安装依赖**

Run:
```bash
cd "C:/Users/win11/Desktop/大创/土木"
npm install
npm install @heroui/react framer-motion react-router-dom react-leaflet leaflet msw
npm install -D @types/leaflet tailwindcss @tailwindcss/vite
```

Expected: 所有依赖安装成功。

- [ ] **Step 3: 配置 Tailwind CSS + NextUI**

Write `src/index.css`:
```css
@import "tailwindcss";
```

Write `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

- [ ] **Step 4: 配置 NextUI Provider 和基础路由**

Write `src/main.tsx`:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import { HeroUIProvider } from '@heroui/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

async function boot() {
  const { worker } = await import('./api/handlers')
  await worker.start({ onUnhandledRequest: 'bypass' })

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <HeroUIProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </HeroUIProvider>
    </React.StrictMode>,
  )
}

boot()
```

Write `src/App.tsx`:
```typescript
import { Routes, Route, Navigate } from 'react-router-dom'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<div>Login placeholder</div>} />
      <Route path="*" element={<div>404</div>} />
    </Routes>
  )
}
```

- [ ] **Step 5: 生成 MSW Service Worker**

Run:
```bash
cd "C:/Users/win11/Desktop/大创/土木"
npx msw init public/ --save
```

Expected: 在 `public/` 下生成 `mockServiceWorker.js`。

- [ ] **Step 6: 创建 MSW handlers 骨架**

Write `src/api/handlers.ts`:
```typescript
import { http, HttpResponse } from 'msw'
import { setupWorker } from 'msw/browser'

export const handlers = [
  http.post('/api/auth/login', () => {
    return HttpResponse.json({ token: 'mock-token', role: 'admin' })
  }),
]

export const worker = setupWorker(...handlers)
```

- [ ] **Step 7: 验证开发服务器启动**

Run:
```bash
cd "C:/Users/win11/Desktop/大创/土木"
npm run dev
```

Expected: Vite 启动成功，浏览器打开 localhost 端口可看到 Login placeholder。

- [ ] **Step 8: 提交**

```bash
cd "C:/Users/win11/Desktop/大创/土木"
git init
git add -A
git commit -m "feat: scaffold project with Vite + React + TS + NextUI + MSW"
```

---

### Task 2: 类型定义 + Mock 数据 + 认证 API

**Files:**
- Create: `src/types/index.ts`
- Create: `src/api/mock-data.ts`
- Create: `src/api/auth.ts`
- Modify: `src/api/handlers.ts`

- [ ] **Step 1: 定义所有 TypeScript 类型**

Write `src/types/index.ts`:
```typescript
export interface User {
  id: string
  username: string
  password: string
  role: 'admin' | 'user'
  name: string
  phone: string
}

export interface Field {
  id: string
  name: string
  area: number
  bounds: [number, number][]
  ownerId: string | null
  crop: string | null
  growthStage: string | null
  plantDate: string | null
}

export interface IrrigationRecord {
  fieldId: string
  date: string
  predicted: number
  actual: number | null
  stage: string
}

export interface WeatherStatus {
  lastUpdate: string
  temperature: number
  humidity: number
  rainfall: number
  status: 'normal' | 'warning'
}

export interface AuthState {
  user: Omit<User, 'password'> | null
  token: string | null
}
```

- [ ] **Step 2: 创建 Mock 数据**

Write `src/api/mock-data.ts`:
```typescript
import type { User, Field, IrrigationRecord, WeatherStatus } from '../types'

export const users: User[] = [
  { id: 'u1', username: 'admin', password: 'admin123', role: 'admin', name: '管理员', phone: '13800000000' },
  { id: 'u2', username: 'farmer1', password: '123456', role: 'user', name: '张农户', phone: '13800000001' },
  { id: 'u3', username: 'farmer2', password: '123456', role: 'user', name: '李农户', phone: '13800000002' },
]

export const fields: Field[] = [
  { id: 'f1', name: '田块 A-01', area: 2.3, bounds: [[30.25, 120.15], [30.26, 120.15], [30.26, 120.16], [30.25, 120.16]], ownerId: 'u2', crop: '小麦', growthStage: '拔节期', plantDate: '2026-03-15' },
  { id: 'f2', name: '田块 A-02', area: 1.8, bounds: [[30.25, 120.17], [30.26, 120.17], [30.26, 120.18], [30.25, 120.18]], ownerId: 'u2', crop: '玉米', growthStage: '抽穗期', plantDate: '2026-05-01' },
  { id: 'f3', name: '田块 B-01', area: 3.1, bounds: [[30.27, 120.15], [30.28, 120.15], [30.28, 120.16], [30.27, 120.16]], ownerId: 'u3', crop: '水稻', growthStage: '分蘖期', plantDate: '2026-04-10' },
  { id: 'f4', name: '田块 B-02', area: 2.7, bounds: [[30.27, 120.17], [30.28, 120.17], [30.28, 120.18], [30.27, 120.18]], ownerId: 'u3', crop: '小麦', growthStage: '灌浆期', plantDate: '2026-02-20' },
  { id: 'f5', name: '田块 C-01', area: 1.5, bounds: [[30.29, 120.15], [30.30, 120.15], [30.30, 120.16], [30.29, 120.16]], ownerId: null, crop: null, growthStage: null, plantDate: null },
  { id: 'f6', name: '田块 C-02', area: 4.2, bounds: [[30.29, 120.17], [30.30, 120.17], [30.30, 120.18], [30.29, 120.18]], ownerId: null, crop: null, growthStage: null, plantDate: null },
]

export const irrigationRecords: IrrigationRecord[] = [
  { fieldId: 'f1', date: '2026-06-10', predicted: 320, actual: null, stage: '拔节期' },
  { fieldId: 'f1', date: '2026-06-17', predicted: 380, actual: null, stage: '拔节期' },
  { fieldId: 'f2', date: '2026-06-10', predicted: 450, actual: null, stage: '抽穗期' },
  { fieldId: 'f2', date: '2026-06-17', predicted: 520, actual: null, stage: '抽穗期' },
  { fieldId: 'f3', date: '2026-06-10', predicted: 280, actual: null, stage: '分蘖期' },
  { fieldId: 'f4', date: '2026-06-10', predicted: 400, actual: null, stage: '灌浆期' },
]

export const weatherStatus: WeatherStatus = {
  lastUpdate: '2026-06-10T08:00:00',
  temperature: 28.5,
  humidity: 65,
  rainfall: 12.3,
  status: 'normal',
}
```

- [ ] **Step 3: 创建认证工具函数**

Write `src/api/auth.ts`:
```typescript
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
```

- [ ] **Step 4: 完善 MSW handlers（认证 + 全量）**

Write `src/api/handlers.ts`:
```typescript
import { http, HttpResponse, delay } from 'msw'
import { setupWorker } from 'msw/browser'
import { users, fields, irrigationRecords, weatherStatus } from './mock-data'
import { generateToken } from './auth'
import type { Field } from '../types'

// 模拟网络延迟
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
    // mock: 从 localStorage 取用户信息（简化验证）
    const user = users[0] // 简化处理
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
    // 简单距离过滤：返回所有田块作为"附近"
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
    // mock: 从 header 中解析简单 userId（简化，实际应该解码 JWT）
    // 这里直接返回所有有 owner 的田块用于 demo
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
```

- [ ] **Step 5: 验证 MSW 拦截工作**

Run dev server 并确认浏览器 Console 中显示 `[MSW] Mocking enabled.`，无报错。

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat: add types, mock data, and complete MSW handlers"
```

---

### Task 3: Auth 模块（登录页 + Context + 路由守卫）

**Files:**
- Create: `src/store/AuthContext.tsx`
- Create: `src/components/ProtectedRoute.tsx`
- Create: `src/pages/Login.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: 创建 AuthContext**

Write `src/store/AuthContext.tsx`:
```typescript
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { saveAuth, getToken, getUser, clearAuth } from '../api/auth'

interface AuthUser {
  id: string
  username: string
  role: string
  name: string
}

interface AuthContextType {
  user: AuthUser | null
  token: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(getUser())
  const [token, setToken] = useState<string | null>(getToken())

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || '登录失败')
    }
    const data = await res.json()
    saveAuth(data.token, data.user)
    setToken(data.token)
    setUser(data.user)
  }, [])

  const logout = useCallback(() => {
    clearAuth()
    setToken(null)
    setUser(null)
  }, [])

  const isAdmin = user?.role === 'admin'

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
```

- [ ] **Step 2: 创建 ProtectedRoute**

Write `src/components/ProtectedRoute.tsx`:
```typescript
import { Navigate } from 'react-router-dom'
import { useAuth } from '../store/AuthContext'

interface Props {
  children: React.ReactNode
  requireAdmin?: boolean
}

export default function ProtectedRoute({ children, requireAdmin = false }: Props) {
  const { user, isAdmin } = useAuth()

  if (!user) return <Navigate to="/login" replace />
  if (requireAdmin && !isAdmin) return <Navigate to="/dashboard" replace />

  return <>{children}</>
}
```

- [ ] **Step 3: 创建 Login 页面**

Write `src/pages/Login.tsx`:
```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Input, Button, Card, CardBody, CardHeader } from '@heroui/react'
import { useAuth } from '../store/AuthContext'

export default function Login() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user) {
    navigate(user.role === 'admin' ? '/admin' : '/dashboard', { replace: true })
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate(username === 'admin' ? '/admin' : '/dashboard', { replace: true })
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0e17]">
      <Card className="w-full max-w-sm bg-[#131820] border border-[#1e2430]">
        <CardHeader className="flex-col gap-1 pt-8 pb-0">
          <h1 className="text-xl font-semibold text-[#c8ccd0]">HYDRO·CS</h1>
          <p className="text-sm text-[#6b7280]">智能灌溉管理平台</p>
        </CardHeader>
        <CardBody className="gap-4 pt-6 pb-8 px-8">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="用户名"
              value={username}
              onValueChange={setUsername}
              variant="bordered"
              classNames={{ input: 'text-[#c8ccd0]', label: 'text-[#6b7280]' }}
            />
            <Input
              label="密码"
              type="password"
              value={password}
              onValueChange={setPassword}
              variant="bordered"
              classNames={{ input: 'text-[#c8ccd0]', label: 'text-[#6b7280]' }}
            />
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <Button type="submit" isLoading={loading} className="bg-[#818cf8] text-white mt-2">
              登录
            </Button>
          </form>
          <p className="text-[10px] text-[#6b7280] text-center mt-2">
            测试账号: admin/admin123 | farmer1/123456 | farmer2/123456
          </p>
        </CardBody>
      </Card>
    </div>
  )
}
```

- [ ] **Step 4: 更新 App.tsx 路由**

Write `src/App.tsx`:
```typescript
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './store/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><div>Admin Dashboard</div></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><div>User Dashboard</div></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
```

- [ ] **Step 5: 验证登录流程**

Run dev server，用 `admin / admin123` 登录，确认跳转到 `/admin` 占位页。用 `farmer1 / 123456` 登录，确认跳转到 `/dashboard`。未登录访问 `/admin` 应重定向回 `/login`。

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat: add auth module - login page, AuthContext, ProtectedRoute"
```

---

### Task 4: 布局框架（三栏 + 侧栏 + 工具条 + 数据面板）

**Files:**
- Create: `src/components/Layout.tsx`
- Create: `src/components/Sidebar.tsx`
- Create: `src/components/ToolBar.tsx`
- Create: `src/components/DataPanel.tsx`
- Modify: `src/App.tsx`
- Modify: `src/index.css`

- [ ] **Step 1: 添加布局基础样式**

Append to `src/index.css`:
```css
@import "tailwindcss";

/* 确保 html/body/root 撑满全屏 */
html, body, #root {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
}
```

- [ ] **Step 2: 创建 Layout 组件**

Write `src/components/Layout.tsx`:
```typescript
import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import ToolBar from './ToolBar'
import DataPanel from './DataPanel'

interface Props {
  children: ReactNode
  /** 左侧菜单项 */
  menuItems: { key: string; label: string; active?: boolean; icon?: string }[]
  /** 当前活跃菜单 key */
  activeMenu: string
  /** 菜单点击回调 */
  onMenuClick: (key: string) => void
  /** 右侧面板数据项 */
  panelItems: { label: string; value: string; highlight?: boolean; sub?: string }[]
  /** 工具栏按钮 */
  tools: { label: string; primary?: boolean; onClick?: () => void }[]
  /** 用户名 */
  username: string
  /** 平台标题 */
  title: string
  /** 是否管理员 */
  isAdmin?: boolean
  /** 退出回调 */
  onLogout: () => void
}

export default function Layout({
  children,
  menuItems,
  activeMenu,
  onMenuClick,
  panelItems,
  tools,
  username,
  title,
  isAdmin,
  onLogout,
}: Props) {
  return (
    <div className="flex flex-col h-screen bg-[#0a0e17] text-[#c8ccd0]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-2.5 bg-[#131820] border-b border-[#1e2430] shrink-0">
        <h1 className="text-sm font-semibold text-[#c8ccd0]">{title}</h1>
        <div className="flex items-center gap-4">
          <span className={`text-xs ${isAdmin ? 'text-amber-400' : 'text-[#9ca3af]'}`}>
            {username}
          </span>
          <button onClick={onLogout} className="text-xs text-[#6b7280] hover:text-[#9ca3af]">
            退出
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <Sidebar items={menuItems} activeKey={activeMenu} onSelect={onMenuClick} />

        {/* Center: content + toolbar */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-hidden">
            {children}
          </div>
          <ToolBar tools={tools} />
        </div>

        {/* Right data panel */}
        <DataPanel items={panelItems} />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 Sidebar 组件**

Write `src/components/Sidebar.tsx`:
```typescript
interface MenuItem {
  key: string
  label: string
  active?: boolean
  icon?: string
}

interface Props {
  items: MenuItem[]
  activeKey: string
  onSelect: (key: string) => void
}

export default function Sidebar({ items, activeKey, onSelect }: Props) {
  return (
    <div className="w-[200px] bg-[#0d1117] border-r border-[#1e2430] flex flex-col shrink-0">
      <div className="px-3 pt-3 pb-2">
        <span className="text-[9px] text-[#6b7280] uppercase tracking-wider">菜单</span>
      </div>
      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onSelect(item.key)}
          className={
            item.key === activeKey
              ? 'mx-2 my-0.5 px-3 py-2 text-xs text-[#c8ccd0] bg-[rgba(129,140,248,0.08)] border-l-2 border-[#818cf8] rounded-r text-left'
              : 'mx-2 my-0.5 px-3 py-2 text-xs text-[#9ca3af] hover:text-[#c8ccd0] text-left rounded'
          }
        >
          {item.icon && <span className="mr-2">{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: 创建 ToolBar 组件**

Write `src/components/ToolBar.tsx`:
```typescript
interface Tool {
  label: string
  primary?: boolean
  onClick?: () => void
}

interface Props {
  tools: Tool[]
}

export default function ToolBar({ tools }: Props) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-[#0d1117] border-t border-[#1e2430] shrink-0">
      <span className="text-[9px] text-[#6b7280] uppercase tracking-wider mr-1">工具</span>
      {tools.map((tool, i) => (
        <button
          key={i}
          onClick={tool.onClick}
          className={
            tool.primary
              ? 'w-[130px] py-1.5 text-[11px] text-[#c8ccd0] bg-[#131820] border border-[#818cf8] rounded-md text-center shrink-0'
              : 'w-[130px] py-1.5 text-[11px] text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md text-center hover:text-[#c8ccd0] shrink-0'
          }
        >
          {tool.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: 创建 DataPanel 组件**

Write `src/components/DataPanel.tsx`:
```typescript
interface DataItem {
  label: string
  value: string
  highlight?: boolean
  sub?: string
}

interface Props {
  items: DataItem[]
}

export default function DataPanel({ items }: Props) {
  return (
    <div className="w-[260px] bg-[#0d1117] border-l border-[#1e2430] p-3.5 overflow-y-auto shrink-0">
      <div className="text-[9px] text-[#6b7280] uppercase tracking-wider mb-3">数据</div>
      {items.map((item, i) => (
        <div
          key={i}
          className={
            item.highlight
              ? 'bg-[#131820] border border-[#1e2430] rounded-md p-3 mb-2'
              : 'bg-[#131820] border border-[#1e2430] rounded-md p-3 mb-2'
          }
        >
          <div className="text-[10px] text-[#6b7280] mb-1">{item.label}</div>
          <div className={item.highlight ? 'text-2xl font-semibold text-[#818cf8]' : 'text-lg font-semibold text-[#c8ccd0]'}>
            {item.value}
          </div>
          {item.sub && <div className="text-[10px] text-[#6b7280] mt-0.5">{item.sub}</div>}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 6: 更新 App.tsx — 接入管理员和用户 Dashboard 布局**

Write `src/App.tsx`:
```typescript
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'

function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={user?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️', active: true },
        { key: 'users', label: '用户管理', icon: '👥' },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="map"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '区域总需水量（今日）', value: '1,280 m³', highlight: true },
        { label: '活跃用户', value: '2' },
        { label: '已绑定田块', value: '6' },
        { label: '灌溉覆盖率', value: '78%' },
      ]}
      tools={[
        { label: '上传气象数据' },
        { label: '参数微调' },
        { label: '导出报表' },
      ]}
    >
      <div className="flex items-center justify-center h-full bg-[#0a0e17]">
        <div className="text-center">
          <div className="text-5xl mb-2 opacity-40">🌍</div>
          <p className="text-xs text-[#6b7280]">卫星地图 — Leaflet</p>
          <p className="text-[10px] text-[#4b5563] mt-1">区/县级以下加载卫星图像</p>
        </div>
      </div>
    </Layout>
  )
}

function UserDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <Layout
      title="HYDRO·CS 灌溉服务"
      username={user?.name ?? ''}
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️', active: true },
        { key: 'fields', label: '我的田块', icon: '🌾' },
        { key: 'records', label: '灌溉记录', icon: '📋' },
      ]}
      activeMenu="map"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/dashboard')
        else if (key === 'fields') navigate('/dashboard/fields')
        else if (key === 'records') navigate('/dashboard/fields')
      }}
      panelItems={[
        { label: '当前位置', value: '余杭区' },
        { label: '选中田块', value: '田块 B-07', sub: '2.3 亩 · 玉米' },
        { label: '本周预测灌溉量', value: '450 m³', highlight: true },
        { label: '作物信息', value: '玉米 · 抽穗期', sub: '播种: 2026-05-15' },
      ]}
      tools={[
        { label: '定位当前位置', primary: true },
        { label: '自动识别田块' },
        { label: '手动框选' },
        { label: '绑定到账号' },
      ]}
    >
      <div className="flex items-center justify-center h-full bg-[#0a0e17]">
        <div className="text-center">
          <div className="text-5xl mb-2 opacity-40">🌍</div>
          <p className="text-xs text-[#6b7280]">卫星地图 — Leaflet</p>
          <p className="text-[10px] text-[#4b5563] mt-1">余杭区 · 卫星图像已加载</p>
        </div>
      </div>
    </Layout>
  )
}

function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center h-full text-sm text-[#6b7280]">
      {title} — 待实现
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute requireAdmin><Placeholder title="用户管理" /></ProtectedRoute>} />
        <Route path="/admin/fields" element={<ProtectedRoute requireAdmin><Placeholder title="田块管理" /></ProtectedRoute>} />
        <Route path="/admin/data" element={<ProtectedRoute requireAdmin><Placeholder title="数据总表" /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute requireAdmin><Placeholder title="参数微调" /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><UserDashboard /></ProtectedRoute>} />
        <Route path="/dashboard/fields" element={<ProtectedRoute><Placeholder title="我的田块" /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
```

- [ ] **Step 7: 验证布局**

Run dev server，以 admin 登录确认：
- 顶栏: 标题 "HYDRO·CS 管理平台" + 用户名（amber 色）+ 退出按钮
- 左侧栏: 5 个菜单项，当前选中"地图总览"有左侧蓝紫边框
- 中间: 地图占位
- 底部: 3 个等宽工具按钮
- 右侧: 4 个数据卡片（顶部高亮紫色）

以 farmer1 登录确认用户端布局类似但菜单/工具/面板内容不同。

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat: add layout framework - Sidebar, ToolBar, DataPanel, 3-column Layout"
```

---

### Task 5: 地图模块（Leaflet + 图层切换 + 搜索定位）

**Files:**
- Create: `src/components/MapView.tsx`
- Create: `src/store/MapContext.tsx`
- Modify: `src/components/Layout.tsx` (add MapContext provider)
- Modify: `src/App.tsx` (use MapView in dashboards)

- [ ] **Step 1: 创建 MapContext**

Write `src/store/MapContext.tsx`:
```typescript
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
```

- [ ] **Step 2: 创建 MapView 组件**

Write `src/components/MapView.tsx`:
```typescript
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../store/MapContext'

// Esri 卫星瓦片
const ESRI_SATELLITE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
// 高德矢量瓦片
const AMAP_VECTOR = 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

export default function MapView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const vectorLayerRef = useRef<L.TileLayer | null>(null)
  const satelliteLayerRef = useRef<L.TileLayer | null>(null)
  const { setZoom, setCenter, setLayerMode } = useMap()

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: [35.8617, 104.1954],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
    })

    // 初始加载矢量图层
    vectorLayerRef.current = L.tileLayer(AMAP_VECTOR, {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 18,
      minZoom: 3,
    }).addTo(map)

    // 预创建卫星图层（不添加）
    satelliteLayerRef.current = L.tileLayer(ESRI_SATELLITE, {
      maxZoom: 20,
      minZoom: 3,
    })

    // 监听缩放变化，切换图层
    map.on('zoomend', () => {
      const z = map.getZoom()
      setZoom(z)
      if (z >= 10) {
        // 区/县级以下 → 卫星图
        if (map.hasLayer(vectorLayerRef.current!)) {
          map.removeLayer(vectorLayerRef.current!)
          map.addLayer(satelliteLayerRef.current!)
          setLayerMode('satellite')
        }
      } else {
        // 省/市级 → 矢量图
        if (map.hasLayer(satelliteLayerRef.current!)) {
          map.removeLayer(satelliteLayerRef.current!)
          map.addLayer(vectorLayerRef.current!)
          setLayerMode('vector')
        }
      }
    })

    // 监听移动
    map.on('moveend', () => {
      const c = map.getCenter()
      setCenter([c.lat, c.lng])
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} className="h-full w-full" />
}
```

- [ ] **Step 3: 在 App.tsx 中用 MapView 替换地图占位符**

Update `src/App.tsx` — 在 AdminDashboard 和 UserDashboard 中将地图占位 div 替换为:
```typescript
import MapView from './components/MapView'
import { MapProvider } from './store/MapContext'

// 在 AdminDashboard 的 Layout children 中:
<MapView />

// 在 UserDashboard 的 Layout children 中:
<MapView />
```

同时用 `<MapProvider>` 包裹两个 Dashboard 组件。更新后的 AdminDashboard:
```typescript
function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 管理平台"
        username={user?.name ?? ''}
        isAdmin
        onLogout={() => { logout(); navigate('/login') }}
        menuItems={[
          { key: 'map', label: '地图总览', icon: '🗺️', active: true },
          { key: 'users', label: '用户管理', icon: '👥' },
          { key: 'fields', label: '田块管理', icon: '🌾' },
          { key: 'data', label: '数据总表', icon: '📊' },
          { key: 'settings', label: '参数微调', icon: '⚙️' },
        ]}
        activeMenu="map"
        onMenuClick={(key) => {
          if (key === 'map') navigate('/admin')
          else if (key === 'users') navigate('/admin/users')
          else if (key === 'fields') navigate('/admin/fields')
          else if (key === 'data') navigate('/admin/data')
          else if (key === 'settings') navigate('/admin/settings')
        }}
        panelItems={[...]}
        tools={[...]}
      >
        <MapView />
      </Layout>
    </MapProvider>
  )
}
```

UserDashboard 同理。

- [ ] **Step 4: 验证地图功能**

Run dev server，确认：
- 地图加载高德矢量瓦片
- 滚轮缩放正常
- 放大到 zoom >= 10 时自动切换为 Esri 卫星图
- 缩小回 zoom < 10 时自动切回矢量图

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: add map module with Leaflet, zoom-based layer switching"
```

---

### Task 6: 用户端田块工作流（识别 → 绑定 → 灌溉预测）

**Files:**
- Modify: `src/components/MapView.tsx` (add field overlay, click interaction)
- Modify: `src/components/DataPanel.tsx` (add selected field info)
- Modify: `src/App.tsx` (add field selection state, bind dialog, irrigation view)
- Create: `src/pages/user/UserDashboard.tsx` (extract from App.tsx)
- Create: `src/pages/user/MyFields.tsx`

- [ ] **Step 1: 提取 UserDashboard 为独立页面组件**

Write `src/pages/user/UserDashboard.tsx`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import { MapProvider } from '../../store/MapContext'
import Layout from '../../components/Layout'
import MapView from '../../components/MapView'
import type { Field } from '../../types'

export default function UserDashboardPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [nearbyFields, setNearbyFields] = useState<Field[]>([])
  const [selectedField, setSelectedField] = useState<Field | null>(null)
  const [myFields, setMyFields] = useState<Field[]>([])
  const [showBindDialog, setShowBindDialog] = useState(false)
  const [crop, setCrop] = useState('')
  const [growthStage, setGrowthStage] = useState('')
  const [plantDate, setPlantDate] = useState('')
  const [irrigation, setIrrigation] = useState<{ predicted: number; date: string }[]>([])

  // 加载附近田块
  useEffect(() => {
    fetch('/api/fields/nearby?lat=30.26&lng=120.17')
      .then(r => r.json())
      .then(setNearbyFields)
  }, [])

  // 加载我的田块
  useEffect(() => {
    fetch('/api/my/fields', { headers: { Authorization: `Bearer mock` } })
      .then(r => r.json())
      .then(setMyFields)
  }, [])

  // 选择田块时加载灌溉预测
  const handleFieldSelect = useCallback(async (field: Field) => {
    setSelectedField(field)
    const res = await fetch(`/api/my/fields/${field.id}/irrigation`)
    const data = await res.json()
    setIrrigation(data)
  }, [])

  // 绑定田块
  const handleBind = useCallback(async () => {
    if (!selectedField || !crop || !growthStage) return
    await fetch('/api/my/fields/bind', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer mock' },
      body: JSON.stringify({
        fieldId: selectedField.id,
        ownerId: user!.id,
        crop,
        growthStage,
        plantDate: plantDate || new Date().toISOString().split('T')[0],
      }),
    })
    setShowBindDialog(false)
    // 刷新
    const res = await fetch('/api/my/fields', { headers: { Authorization: `Bearer mock` } })
    setMyFields(await res.json())
  }, [selectedField, crop, growthStage, plantDate, user])

  const handleLogout = () => { logout(); navigate('/login') }

  const panelItems = [
    { label: '当前位置', value: '余杭区' },
    ...(selectedField
      ? [
          { label: '选中田块', value: selectedField.name, sub: `${selectedField.area} 亩${selectedField.crop ? ' · ' + selectedField.crop : ''}` },
          ...(irrigation.length > 0
            ? [{ label: '本周预测灌溉量', value: `${irrigation[0].predicted} m³`, highlight: true as const }]
            : []),
          ...(selectedField.crop
            ? [{ label: '作物信息', value: `${selectedField.crop} · ${selectedField.growthStage}`, sub: `播种: ${selectedField.plantDate}` }]
            : []),
        ]
      : [{ label: '选中田块', value: '—', sub: '点击地图上的田块' }]),
  ]

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 灌溉服务"
        username={user?.name ?? ''}
        onLogout={handleLogout}
        menuItems={[
          { key: 'map', label: '地图总览', icon: '🗺️', active: true },
          { key: 'fields', label: '我的田块', icon: '🌾' },
          { key: 'records', label: '灌溉记录', icon: '📋' },
        ]}
        activeMenu="map"
        onMenuClick={(key) => {
          if (key === 'map') navigate('/dashboard')
          else if (key === 'fields') navigate('/dashboard/fields')
          else navigate('/dashboard/fields')
        }}
        panelItems={panelItems}
        tools={[
          { label: '定位当前位置', primary: true },
          { label: '自动识别田块', onClick: () => {
            // 刷新附近田块
            fetch('/api/fields/nearby?lat=30.26&lng=120.17')
              .then(r => r.json())
              .then(setNearbyFields)
          }},
          { label: '手动框选' },
          { label: '绑定到账号', onClick: () => {
            if (selectedField && !selectedField.ownerId) {
              setShowBindDialog(true)
            }
          }},
        ]}
      >
        <MapView
          fields={nearbyFields}
          selectedFieldId={selectedField?.id}
          onFieldClick={handleFieldSelect}
        />

        {/* 绑定对话框 */}
        {showBindDialog && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-50">
            <div className="bg-[#131820] border border-[#1e2430] rounded-lg p-6 w-80">
              <h3 className="text-sm font-semibold text-[#c8ccd0] mb-4">绑定田块 {selectedField?.name}</h3>
              <div className="flex flex-col gap-3">
                <div>
                  <label className="text-[10px] text-[#6b7280]">作物种类</label>
                  <input value={crop} onChange={e => setCrop(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1"
                    placeholder="如: 小麦" />
                </div>
                <div>
                  <label className="text-[10px] text-[#6b7280]">生长周期</label>
                  <input value={growthStage} onChange={e => setGrowthStage(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1"
                    placeholder="如: 拔节期" />
                </div>
                <div>
                  <label className="text-[10px] text-[#6b7280]">播种日期</label>
                  <input type="date" value={plantDate} onChange={e => setPlantDate(e.target.value)}
                    className="w-full bg-[#0a0e17] border border-[#1e2430] rounded p-2 text-xs text-[#c8ccd0] mt-1" />
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                <button onClick={() => setShowBindDialog(false)}
                  className="flex-1 py-1.5 text-xs border border-[#1e2430] text-[#9ca3af] rounded-md">取消</button>
                <button onClick={handleBind}
                  className="flex-1 py-1.5 text-xs bg-[#818cf8] text-white rounded-md">确认绑定</button>
              </div>
            </div>
          </div>
        )}
      </Layout>
    </MapProvider>
  )
}
```

- [ ] **Step 2: 更新 MapView 支持田块叠加和点击**

Modify `src/components/MapView.tsx` — add props and field overlay logic:

```typescript
import type { Field } from '../types'

interface Props {
  fields?: Field[]
  selectedFieldId?: string
  onFieldClick?: (field: Field) => void
}

export default function MapView({ fields = [], selectedFieldId, onFieldClick }: Props) {
  // ... existing refs ...

  // 田块 GeoJSON 叠加
  useEffect(() => {
    if (!mapRef.current || fields.length === 0) return

    const geoLayer = L.geoJSON(
      {
        type: 'FeatureCollection',
        features: fields.map(f => ({
          type: 'Feature' as const,
          properties: { id: f.id, name: f.name, crop: f.crop, ownerId: f.ownerId },
          geometry: {
            type: 'Polygon',
            coordinates: [[...f.bounds.map(b => [b[1], b[0]]), [f.bounds[0][1], f.bounds[0][0]]]],
          },
        })),
      },
      {
        style: (feature) => {
          const isSelected = feature?.properties.id === selectedFieldId
          const hasOwner = !!feature?.properties.ownerId
          return {
            fillColor: isSelected ? '#818cf8' : hasOwner ? '#fbbf24' : '#4ade80',
            fillOpacity: 0.3,
            color: isSelected ? '#818cf8' : hasOwner ? '#fbbf24' : '#4ade80',
            weight: isSelected ? 3 : 1,
          }
        },
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(feature.properties.name + (feature.properties.crop ? ` · ${feature.properties.crop}` : ''))
          layer.on('click', () => {
            const field = fields.find(f => f.id === feature.properties.id)
            if (field && onFieldClick) onFieldClick(field)
          })
        },
      }
    ).addTo(mapRef.current)

    return () => {
      mapRef.current?.removeLayer(geoLayer)
    }
  }, [fields, selectedFieldId, onFieldClick])
  // ...
}
```

- [ ] **Step 3: 创建 MyFields 页面**

Write `src/pages/user/MyFields.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { Field } from '../../types'

export default function MyFieldsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [fields, setFields] = useState<Field[]>([])
  const [irrigationData, setIrrigationData] = useState<Record<string, { predicted: number; date: string }[]>>({})

  useEffect(() => {
    fetch('/api/my/fields', { headers: { Authorization: 'Bearer mock' } })
      .then(r => r.json())
      .then(data => {
        setFields(data)
        // 加载每个田块的灌溉预测
        data.forEach((f: Field) => {
          fetch(`/api/my/fields/${f.id}/irrigation`)
            .then(r => r.json())
            .then(records => {
              setIrrigationData(prev => ({ ...prev, [f.id]: records }))
            })
        })
      })
  }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <Layout
      title="HYDRO·CS 灌溉服务"
      username={user?.name ?? ''}
      onLogout={handleLogout}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'fields', label: '我的田块', icon: '🌾', active: true },
        { key: 'records', label: '灌溉记录', icon: '📋' },
      ]}
      activeMenu="fields"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/dashboard')
        else navigate('/dashboard/fields')
      }}
      panelItems={[
        { label: '已绑定田块', value: `${fields.length}` },
        { label: '总面积', value: `${fields.reduce((s, f) => s + f.area, 0).toFixed(1)} 亩` },
      ]}
      tools={[
        { label: '返回地图', onClick: () => navigate('/dashboard'), primary: true },
      ]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">我的田块</h2>
        {fields.length === 0 ? (
          <p className="text-xs text-[#6b7280]">暂无绑定田块，请在地图上框选并绑定。</p>
        ) : (
          <div className="flex flex-col gap-3">
            {fields.map(f => (
              <div key={f.id} className="bg-[#131820] border border-[#1e2430] rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-sm text-[#c8ccd0] font-medium">{f.name}</h3>
                    <p className="text-xs text-[#6b7280]">{f.area} 亩 · {f.crop} · {f.growthStage}</p>
                    <p className="text-[10px] text-[#6b7280]">播种: {f.plantDate}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] text-[#6b7280]">本周预测灌溉</div>
                    <div className="text-lg font-semibold text-[#818cf8]">
                      {irrigationData[f.id]?.[0]?.predicted ?? '—'} m³
                    </div>
                  </div>
                </div>
                {/* 灌溉预测表 */}
                {irrigationData[f.id] && irrigationData[f.id].length > 0 && (
                  <table className="w-full mt-3 text-[10px] text-[#9ca3af] border-t border-[#1e2430] pt-2">
                    <thead>
                      <tr className="text-[#6b7280]">
                        <th className="text-left py-1">日期</th>
                        <th className="text-left py-1">生长阶段</th>
                        <th className="text-right py-1">预测灌溉量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {irrigationData[f.id].map((r, i) => (
                        <tr key={i}>
                          <td className="py-1">{r.date}</td>
                          <td className="py-1">{f.growthStage}</td>
                          <td className="py-1 text-right text-[#818cf8]">{r.predicted} m³</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
```

- [ ] **Step 4: 更新 App.tsx 使用独立页面组件**

Modify `src/App.tsx`:
- Remove inline AdminDashboard and UserDashboard definitions
- Import `UserDashboardPage` and `MyFieldsPage`
- Update routes:
```typescript
import UserDashboardPage from './pages/user/UserDashboard'
import MyFieldsPage from './pages/user/MyFields'

// In Routes:
<Route path="/dashboard" element={<ProtectedRoute><UserDashboardPage /></ProtectedRoute>} />
<Route path="/dashboard/fields" element={<ProtectedRoute><MyFieldsPage /></ProtectedRoute>} />
```

- [ ] **Step 5: 验证田块工作流**

Run dev server，以 farmer1 登录：
- 地图上应显示田块 GeoJSON 叠加层（绿色=空闲，黄色=已有主）
- 点击田块，右侧面板更新选中田块信息
- 点击"自动识别田块"工具按钮刷新列表
- 点击"绑定到账号"，弹出绑定对话框
- 输入作物种类和生长周期，确认绑定
- 切换到"我的田块"页面，查看已绑定田块和灌溉预测表

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat: add user field workflow - identify, select, bind, irrigation prediction"
```

---

### Task 7: 管理员端页面（用户管理 + 田块管理 + 数据总表 + 设置）

**Files:**
- Create: `src/pages/admin/AdminDashboard.tsx`
- Create: `src/pages/admin/UserManage.tsx`
- Create: `src/pages/admin/FieldManage.tsx`
- Create: `src/pages/admin/DataOverview.tsx`
- Create: `src/pages/admin/Settings.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: 创建 AdminDashboard 页面**

Write `src/pages/admin/AdminDashboard.tsx`:
```typescript
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import { MapProvider } from '../../store/MapContext'
import Layout from '../../components/Layout'
import MapView from '../../components/MapView'

export default function AdminDashboardPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <MapProvider>
      <Layout
        title="HYDRO·CS 管理平台"
        username={user?.name ?? ''}
        isAdmin
        onLogout={handleLogout}
        menuItems={[
          { key: 'map', label: '地图总览', icon: '🗺️', active: true },
          { key: 'users', label: '用户管理', icon: '👥' },
          { key: 'fields', label: '田块管理', icon: '🌾' },
          { key: 'data', label: '数据总表', icon: '📊' },
          { key: 'settings', label: '参数微调', icon: '⚙️' },
        ]}
        activeMenu="map"
        onMenuClick={(key) => {
          if (key === 'map') navigate('/admin')
          else if (key === 'users') navigate('/admin/users')
          else if (key === 'fields') navigate('/admin/fields')
          else if (key === 'data') navigate('/admin/data')
          else if (key === 'settings') navigate('/admin/settings')
        }}
        panelItems={[
          { label: '区域总需水量（今日）', value: '1,280 m³', highlight: true },
          { label: '活跃用户', value: '2' },
          { label: '已绑定田块', value: '6' },
          { label: '灌溉覆盖率', value: '78%' },
        ]}
        tools={[
          { label: '上传气象数据' },
          { label: '参数微调' },
          { label: '导出报表' },
        ]}
      >
        <MapView />
      </Layout>
    </MapProvider>
  )
}
```

- [ ] **Step 2: 创建 UserManage 页面**

Write `src/pages/admin/UserManage.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { User } from '../../types'

export default function UserManagePage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState<Omit<User, 'password'>[]>([])

  useEffect(() => {
    fetch('/api/admin/users')
      .then(r => r.json())
      .then(setUsers)
  }, [])

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥', active: true },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="users"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '用户总数', value: `${users.length}` },
        { label: '管理员', value: `${users.filter(u => u.role === 'admin').length}` },
        { label: '农户', value: `${users.filter(u => u.role === 'user').length}` },
      ]}
      tools={[]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">用户管理</h2>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">用户名</th>
              <th className="text-left py-2 px-3">姓名</th>
              <th className="text-left py-2 px-3">角色</th>
              <th className="text-left py-2 px-3">电话</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[#131820]">
                <td className="py-2 px-3 text-[#c8ccd0]">{u.username}</td>
                <td className="py-2 px-3">{u.name}</td>
                <td className="py-2 px-3">
                  <span className={u.role === 'admin' ? 'text-amber-400' : 'text-[#9ca3af]'}>
                    {u.role === 'admin' ? '管理员' : '农户'}
                  </span>
                </td>
                <td className="py-2 px-3">{u.phone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
```

- [ ] **Step 3: 创建 FieldManage 页面**

Write `src/pages/admin/FieldManage.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'
import type { Field } from '../../types'

export default function FieldManagePage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [fields, setFields] = useState<Field[]>([])

  useEffect(() => {
    fetch('/api/admin/fields').then(r => r.json()).then(setFields)
  }, [])

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥' },
        { key: 'fields', label: '田块管理', icon: '🌾', active: true },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="fields"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '田块总数', value: `${fields.length}` },
        { label: '已绑定', value: `${fields.filter(f => f.ownerId).length}` },
        { label: '未绑定', value: `${fields.filter(f => !f.ownerId).length}` },
      ]}
      tools={[]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">田块管理</h2>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">编号</th>
              <th className="text-left py-2 px-3">面积(亩)</th>
              <th className="text-left py-2 px-3">绑定用户</th>
              <th className="text-left py-2 px-3">作物</th>
              <th className="text-left py-2 px-3">生长周期</th>
            </tr>
          </thead>
          <tbody>
            {fields.map(f => (
              <tr key={f.id} className="border-b border-[#131820]">
                <td className="py-2 px-3 text-[#c8ccd0]">{f.name}</td>
                <td className="py-2 px-3">{f.area}</td>
                <td className="py-2 px-3">{f.ownerId ? (f.ownerId === 'u2' ? '张农户' : '李农户') : <span className="text-[#34d399]">空闲</span>}</td>
                <td className="py-2 px-3">{f.crop || '—'}</td>
                <td className="py-2 px-3">{f.growthStage || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
```

- [ ] **Step 4: 创建 DataOverview 页面**

Write `src/pages/admin/DataOverview.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'

interface Stats {
  activeUsers: number
  boundFields: number
  totalFields: number
  totalPredictedWater: number
  coverageRate: number
}

export default function DataOverviewPage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    fetch('/api/admin/stats').then(r => r.json()).then(setStats)
  }, [])

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥' },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊', active: true },
        { key: 'settings', label: '参数微调', icon: '⚙️' },
      ]}
      activeMenu="data"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else if (key === 'settings') navigate('/admin/settings')
      }}
      panelItems={[
        { label: '区域总需水量', value: stats ? `${stats.totalPredictedWater} m³` : '—', highlight: true },
        { label: '活跃用户', value: `${stats?.activeUsers ?? '—'}` },
        { label: '已绑定田块', value: `${stats?.boundFields ?? '—'} / ${stats?.totalFields ?? '—'}` },
        { label: '灌溉覆盖率', value: `${stats?.coverageRate ?? '—'}%` },
      ]}
      tools={[
        { label: '导出报表' },
      ]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">数据总表</h2>
        <p className="text-xs text-[#6b7280] mb-4">
          区域总需水量: <span className="text-[#818cf8] font-semibold">{stats?.totalPredictedWater ?? '—'} m³</span> ·
          灌溉覆盖率: <span className="text-[#c8ccd0] font-semibold">{stats?.coverageRate ?? '—'}%</span>
        </p>
        <table className="w-full text-xs text-[#9ca3af] border-collapse">
          <thead>
            <tr className="text-[#6b7280] border-b border-[#1e2430]">
              <th className="text-left py-2 px-3">用户</th>
              <th className="text-left py-2 px-3">田块</th>
              <th className="text-left py-2 px-3">作物</th>
              <th className="text-left py-2 px-3">周期</th>
              <th className="text-right py-2 px-3">预测灌溉量</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">张农户</td><td className="py-2 px-3">田块 A-01</td>
              <td className="py-2 px-3">小麦</td><td className="py-2 px-3">拔节期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">320 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">张农户</td><td className="py-2 px-3">田块 A-02</td>
              <td className="py-2 px-3">玉米</td><td className="py-2 px-3">抽穗期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">450 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">李农户</td><td className="py-2 px-3">田块 B-01</td>
              <td className="py-2 px-3">水稻</td><td className="py-2 px-3">分蘖期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">280 m³</td>
            </tr>
            <tr className="border-b border-[#131820]">
              <td className="py-2 px-3">李农户</td><td className="py-2 px-3">田块 B-02</td>
              <td className="py-2 px-3">小麦</td><td className="py-2 px-3">灌浆期</td>
              <td className="py-2 px-3 text-right text-[#818cf8]">400 m³</td>
            </tr>
            <tr className="border-b border-[#1e2430]">
              <td className="py-2 px-3 text-[#c8ccd0] font-semibold" colSpan={4}>区域总需水量</td>
              <td className="py-2 px-3 text-right text-[#34d399] font-semibold">{stats?.totalPredictedWater ?? '—'} m³</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Layout>
  )
}
```

- [ ] **Step 5: 创建 Settings 页面（按钮占位）**

Write `src/pages/admin/Settings.tsx`:
```typescript
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/AuthContext'
import Layout from '../../components/Layout'

export default function SettingsPage() {
  const { user: admin, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <Layout
      title="HYDRO·CS 管理平台"
      username={admin?.name ?? ''}
      isAdmin
      onLogout={() => { logout(); navigate('/login') }}
      menuItems={[
        { key: 'map', label: '地图总览', icon: '🗺️' },
        { key: 'users', label: '用户管理', icon: '👥' },
        { key: 'fields', label: '田块管理', icon: '🌾' },
        { key: 'data', label: '数据总表', icon: '📊' },
        { key: 'settings', label: '参数微调', icon: '⚙️', active: true },
      ]}
      activeMenu="settings"
      onMenuClick={(key) => {
        if (key === 'map') navigate('/admin')
        else if (key === 'users') navigate('/admin/users')
        else if (key === 'fields') navigate('/admin/fields')
        else if (key === 'data') navigate('/admin/data')
        else navigate('/admin/settings')
      }}
      panelItems={[
        { label: '气象数据', value: '正常', sub: '更新: 2026-06-10 08:00' },
        { label: '温度', value: '28.5°C' },
        { label: '湿度', value: '65%' },
        { label: '降雨量', value: '12.3 mm' },
      ]}
      tools={[
        { label: '上传气象数据' },
        { label: '参数微调' },
      ]}
    >
      <div className="p-6 overflow-y-auto">
        <h2 className="text-sm font-semibold text-[#c8ccd0] mb-4">参数微调</h2>
        <p className="text-xs text-[#6b7280] mb-4">以下功能按钮预留，暂无实际功能。</p>
        <div className="flex flex-col gap-3 max-w-sm">
          <button className="w-full py-2 text-xs text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md hover:text-[#c8ccd0]">
            上传最新气象数据
          </button>
          <button className="w-full py-2 text-xs text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md hover:text-[#c8ccd0]">
            灌溉模型参数调整
          </button>
          <button className="w-full py-2 text-xs text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md hover:text-[#c8ccd0]">
            田块识别阈值设置
          </button>
          <button className="w-full py-2 text-xs text-[#9ca3af] bg-[#131820] border border-[#1e2430] rounded-md hover:text-[#c8ccd0]">
            系统通知配置
          </button>
        </div>
      </div>
    </Layout>
  )
}
```

- [ ] **Step 6: 更新 App.tsx 路由**

Write `src/App.tsx`:
```typescript
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './store/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import AdminDashboardPage from './pages/admin/AdminDashboard'
import UserManagePage from './pages/admin/UserManage'
import FieldManagePage from './pages/admin/FieldManage'
import DataOverviewPage from './pages/admin/DataOverview'
import SettingsPage from './pages/admin/Settings'
import UserDashboardPage from './pages/user/UserDashboard'
import MyFieldsPage from './pages/user/MyFields'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboardPage /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute requireAdmin><UserManagePage /></ProtectedRoute>} />
        <Route path="/admin/fields" element={<ProtectedRoute requireAdmin><FieldManagePage /></ProtectedRoute>} />
        <Route path="/admin/data" element={<ProtectedRoute requireAdmin><DataOverviewPage /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute requireAdmin><SettingsPage /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><UserDashboardPage /></ProtectedRoute>} />
        <Route path="/dashboard/fields" element={<ProtectedRoute><MyFieldsPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
```

- [ ] **Step 7: 验证管理员页面**

Run dev server，以 admin 登录：
- 地图总览: 地图正常显示
- 用户管理: 3 个用户列表
- 田块管理: 6 个田块列表（含绑定状态）
- 数据总表: 统计卡片 + 详细数据表
- 参数微调: 4 个无功能按钮

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat: add admin pages - user/field management, data overview, settings"
```

---

### Task 8: 主题切换 + 地图搜索 + 收尾

**Files:**
- Modify: `src/components/Layout.tsx` (add theme toggle)
- Modify: `src/components/MapView.tsx` (add search control)
- Modify: `src/main.tsx` (add ThemeProvider)
- Create: `README.md`

- [ ] **Step 1: NextUI 主题切换**

Modify `src/main.tsx` — Add useState for theme and pass to HeroUIProvider:
```typescript
import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { HeroUIProvider } from '@heroui/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

function Root() {
  const [isDark, setIsDark] = useState(true)

  return (
    <HeroUIProvider className={isDark ? 'dark' : 'light'}>
      <BrowserRouter>
        <App isDark={isDark} onToggleTheme={() => setIsDark(!isDark)} />
      </BrowserRouter>
    </HeroUIProvider>
  )
}

async function boot() {
  const { worker } = await import('./api/handlers')
  await worker.start({ onUnhandledRequest: 'bypass' })

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode><Root /></React.StrictMode>,
  )
}

boot()
```

- [ ] **Step 2: 更新 App.tsx 传递主题 prop**

Modify `src/App.tsx`:
```typescript
interface Props {
  isDark: boolean
  onToggleTheme: () => void
}

export default function App({ isDark, onToggleTheme }: Props) {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login isDark={isDark} onToggleTheme={onToggleTheme} />} />
        {/* ... other routes need isDark/onToggleTheme passed through or use context */}
      </Routes>
    </AuthProvider>
  )
}
```

Better approach: Create a ThemeContext instead of prop drilling.

Write `src/store/ThemeContext.tsx`:
```typescript
import { createContext, useContext, useState, type ReactNode } from 'react'

interface ThemeContextType {
  isDark: boolean
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextType>({ isDark: true, toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(true)
  return (
    <ThemeContext.Provider value={{ isDark, toggle: () => setIsDark(!isDark) }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
```

In `src/main.tsx`:
```typescript
import { ThemeProvider } from './store/ThemeContext'
// wrap:
<ThemeProvider>
  <HeroUIProvider>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </HeroUIProvider>
</ThemeProvider>
```

- [ ] **Step 3: Layout 顶栏添加主题切换按钮**

Modify `src/components/Layout.tsx` — add theme toggle in top bar:
```typescript
import { useTheme } from '../store/ThemeContext'

// In top bar, after username:
const { isDark, toggle } = useTheme()
// ...
<button onClick={toggle} className="text-xs px-2.5 py-1 bg-[#1e2430] rounded text-[#9ca3af]">
  {isDark ? '☀️ 亮色' : '🌙 暗色'}
</button>
```

- [ ] **Step 4: MapView 添加搜索定位**

Modify `src/components/MapView.tsx` — add search input overlay:
```typescript
import { useState } from 'react'

// Inside MapView component:
const [searchText, setSearchText] = useState('')

const handleSearch = async () => {
  if (!searchText.trim() || !mapRef.current) return
  // 使用 Nominatim 地理编码（免费、无需 Key）
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchText)}&limit=1`
    )
    const data = await res.json()
    if (data[0]) {
      mapRef.current.setView([parseFloat(data[0].lat), parseFloat(data[0].lon)], 14)
    }
  } catch {
    // mock fallback: 定位到杭州
    mapRef.current.setView([30.25, 120.17], 14)
  }
}

// In JSX, overlay on top of map div:
{/* Search bar */}
<div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex gap-2">
  <input
    value={searchText}
    onChange={e => setSearchText(e.target.value)}
    onKeyDown={e => e.key === 'Enter' && handleSearch()}
    placeholder="搜索地点..."
    className="w-60 px-3 py-1.5 text-xs bg-[#131820] border border-[#1e2430] rounded-md text-[#9ca3af] outline-none focus:border-[#818cf8]"
  />
  <button onClick={handleSearch}
    className="px-3 py-1.5 text-xs bg-[#131820] border border-[#1e2430] rounded-md text-[#9ca3af] hover:text-[#c8ccd0]">
    搜索
  </button>
</div>
```

Wrap MapView's return in a relative container:
```typescript
return (
  <div className="relative h-full w-full">
    <div ref={containerRef} className="h-full w-full" />
    {/* Search overlay */}
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex gap-2">
      ...
    </div>
  </div>
)
```

- [ ] **Step 5: 创建 README.md**

Write `README.md`:
```markdown
# HydroCS 智能灌溉管理平台

面向农业灌溉管理的 Web 前端应用，分为管理员端和用户端。

## 技术栈

- React 18 + TypeScript + Vite
- NextUI (HeroUI) + Tailwind CSS
- Leaflet + react-leaflet
- MSW (Mock Service Worker)

## 快速启动

```bash
npm install
npm run dev
```

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| farmer1 | 123456 | 农户 |
| farmer2 | 123456 | 农户 |

## 功能概览

### 管理员端
- 地图总览：Leaflet 地图，缩放自动切换卫星图
- 用户管理：查看用户列表
- 田块管理：查看全部田块及绑定状态
- 数据总表：区域灌溉预测数据、需水量统计
- 参数微调：功能按钮占位

### 用户端
- 地图总览：定位、搜索、田块识别叠加
- 田块框选与绑定：选择田块 → 录入作物信息 → 绑定账号
- 灌溉预测：查看不同时期的预测灌溉量（模拟数据）
- 我的田块：已绑定田块管理

## 项目结构

```
src/
├── api/          # MSW handlers + mock data
├── components/   # Layout, Sidebar, MapView, ToolBar, DataPanel
├── pages/        # admin/ + user/ 页面组件
├── store/        # AuthContext, MapContext, ThemeContext
└── types/        # TypeScript 类型定义
```
```

- [ ] **Step 6: 验证主题切换和搜索**

Run dev server:
- 点击顶栏"亮色"按钮，确认主题切换为浅色
- 在搜索框输入"杭州"并回车/点击搜索，确认地图定位过去
- 确认所有页面功能正常

- [ ] **Step 7: 构建验证**

Run:
```bash
npm run build
```

Expected: Build 成功，无 TypeScript 错误。

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat: add theme toggle, map search, README"
```
