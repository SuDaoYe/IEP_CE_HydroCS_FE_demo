/** Verifies the offline path: app shell from the SW cache + fields from IndexedDB. */
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('.scratch')
fs.mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8000'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1280, height: 860 } })
const page = await context.newPage()

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('input[autocomplete="username"]', 'farmer1')
await page.fill('input[autocomplete="current-password"]', '123456')
await page.click('button[type="submit"]')
await page.waitForURL((u) => u.pathname === '/', { timeout: 20000 })
await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 20000 })
await page.waitForTimeout(6000)

const swReady = await page.evaluate(async () => {
  if (!('serviceWorker' in navigator)) return 'unsupported'
  const registration = await navigator.serviceWorker.ready.catch(() => null)
  return registration ? 'active' : 'pending'
})
console.log('service worker:', swReady)

const onlineFields = await page.locator('section button').filter({ hasText: '田' }).count()
console.log('online field buttons:', onlineFields)

await context.setOffline(true)
await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForTimeout(5000)

const offline = await page.evaluate(() => ({
  title: document.title,
  hasCanvas: Boolean(document.querySelector('canvas.maplibregl-canvas')),
  bodyText: document.body.innerText.replace(/\s+/g, ' ').slice(0, 220),
}))
console.log('offline shell:', JSON.stringify(offline, null, 2))
await page.screenshot({ path: path.join(OUT, '11-offline.png') })

await context.setOffline(false)
await browser.close()
