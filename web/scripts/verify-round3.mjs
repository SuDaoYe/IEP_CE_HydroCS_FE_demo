/** Verifies: village-level search, weekly/monthly rollups, deep-zoom alignment. */
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
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})
page.on('pageerror', (err) => errors.push(err.message))

async function shot(name) {
  await page.screenshot({ path: path.join(OUT, name) })
  console.log('  shot:', name)
}

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('input[autocomplete="username"]', 'farmer1')
await page.fill('input[autocomplete="current-password"]', '123456')
await page.click('button[type="submit"]')
await page.waitForURL((u) => u.pathname === '/', { timeout: 20000 })
await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 25000 })
await page.waitForTimeout(6000)

// 1) village-level fuzzy search
const search = page.locator('header input').first()
await search.click()
await search.fill('张家庄')
await page.waitForTimeout(1400)
await shot('30-search-village.png')
const rows = page.locator('header ul li')
console.log('  village hits:', await rows.count())
console.log('  first hit:', (await rows.first().innerText()).replace(/\s+/g, ' '))
await page.keyboard.press('Escape')
await search.fill('')
await page.waitForTimeout(400)

// 2) weekly / monthly rollups in the detail panel
const card = page.locator('section button').filter({ hasText: '东片一号田' }).first()
await card.click()
await page.waitForTimeout(2600)
await page.getByRole('button', { name: '30 天' }).click()
await page.waitForTimeout(2200)
await page.getByRole('button', { name: '周尺度' }).click()
await page.waitForTimeout(800)
await shot('31-detail-weekly.png')
await page.getByRole('button', { name: '90 天' }).click()
await page.waitForTimeout(2200)
await page.getByRole('button', { name: '月尺度' }).click()
await page.waitForTimeout(800)
await shot('32-detail-monthly.png')
const buckets = await page.locator('aside').last().innerText()
console.log('  monthly panel snippet:', buckets.replace(/\s+/g, ' ').slice(0, 160))

// 3) deep zoom alignment over the demo parcels
await page.getByRole('button', { name: '日尺度' }).click()
await page.evaluate(() => {
  const map = window.__hcMap
  if (!map) return
  const target = Math.min((map.getZoom() ?? 16) + 3, 19)
  map.jumpTo({ center: map.getCenter(), zoom: target })
})
await page.waitForTimeout(8000)
await shot('33-deep-zoom.png')
const probe = await page.evaluate(() => {
  const map = window.__hcMap
  if (!map) return null
  const centre = map.getCenter()
  const hits = map.queryRenderedFeatures(map.project(centre), { layers: ['fields-fill', 'selected-fill'] })
  return { zoom: Math.round(map.getZoom() * 10) / 10, centredOnField: hits.length > 0, tiles: map.areTilesLoaded() }
})
console.log('  deep zoom:', JSON.stringify(probe))

await browser.close()
console.log('\nconsole errors:', errors.length)
errors.slice(0, 8).forEach((line) => console.log(' -', line.slice(0, 150)))
