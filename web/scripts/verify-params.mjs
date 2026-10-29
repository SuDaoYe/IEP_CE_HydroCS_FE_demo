/** Verifies region-scoped parameter editing end to end. */
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('.scratch')
fs.mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8000'
const errors = []

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
const page = await context.newPage()
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text())
})
page.on('pageerror', (e) => errors.push(e.message))

async function shot(name) {
  await page.screenshot({ path: path.join(OUT, name) })
  console.log('  shot:', name)
}

async function login(user, pass) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[autocomplete="username"]', user)
  await page.fill('input[autocomplete="current-password"]', pass)
  await page.click('button[type="submit"]')
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 })
}

async function probeDemand() {
  return page.evaluate(async () => {
    const token = localStorage.getItem('hydrocs.token')
    const res = await fetch('/api/v1/fields', { headers: { Authorization: `Bearer ${token}` } })
    const fields = await res.json()
    const plan = await fetch(`/api/v1/fields/${fields[0].id}/irrigation?days=7`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const body = await plan.json()
    return {
      name: fields[0].name,
      volume: body.totals.volume_m3,
      scope: body.parameter_scope.scope,
      kc_scale: body.parameter_scope.values.kc_scale,
      source: body.parameter_scope.sources.kc_scale,
    }
  })
}

// 1) farmer baseline
await login('farmer1', '123456')
await page.waitForSelector('section button', { timeout: 20000 })
await page.waitForTimeout(3000)
const before = await probeDemand()
console.log('  baseline:', JSON.stringify(before))

// 2) admin edits the city scope
await page.evaluate(() => localStorage.clear())
await login('admin', 'admin123')
await page.waitForTimeout(2000)
await page.getByRole('button', { name: '模型参数' }).click()
await page.waitForTimeout(2500)
await shot('40-params-global.png')

const picker = page.locator('input[placeholder*="为该地区"]').first()
await picker.click()
await picker.fill('东营')
await page.waitForTimeout(1500)
const firstResult = page.locator('ul li button').first()
await firstResult.click()
await page.waitForTimeout(2500)
await shot('41-params-city.png')

const header = await page.locator('body').innerText()
const scopeLine = header.replace(/\s+/g, ' ').match(/(全局默认|山东省东营市) · 生效参数/)
console.log('  panel scope:', scopeLine ? scopeLine[0] : 'not found')

// 3) bump Kc_scale at the city scope
const numeric = page.locator('input[type="number"]').first()
const current = await numeric.inputValue()
console.log('  kc_scale before edit:', current)
await numeric.fill('0.9')
await page.getByRole('button', { name: '保存本层' }).click()
await page.waitForTimeout(2500)
await shot('42-params-saved.png')

// 4) farmer sees 1.2 attributed to the city
await page.evaluate(() => localStorage.clear())
await login('farmer1', '123456')
await page.waitForTimeout(2500)
const after = await probeDemand()
console.log('  after:', JSON.stringify(after))
console.log('  demand rose:', after.volume > before.volume)

await browser.close()
console.log('\nconsole errors:', errors.length)
errors.slice(0, 8).forEach((line) => console.log(' -', line.slice(0, 150)))
