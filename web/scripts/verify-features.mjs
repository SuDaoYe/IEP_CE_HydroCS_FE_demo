/** Verifies the new flows: fuzzy search, docked editor, admin tabs. */
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

async function login(username, password) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[autocomplete="username"]', username)
  await page.fill('input[autocomplete="current-password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 })
}

// ---------- farmer: search + docked editor ----------
await login('farmer1', '123456')
await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 25000 })
await page.waitForTimeout(6000)

const search = page.locator('header input').first()
await search.click()
await search.fill('垦利')
await page.waitForTimeout(1200)
await shot('20-search-dropdown.png')
console.log('  hits:', await page.locator('header ul li').count())

await page.keyboard.press('Enter')
await page.waitForTimeout(9000)
await shot('21-search-jumped.png')
const tilesOk = await page.evaluate(() => {
  const map = window.__hcMap
  return map ? { loaded: map.areTilesLoaded(), zoom: map.getZoom() } : null
})
console.log('  after jump:', JSON.stringify(tilesOk))

// draw mode → docked panel, map must stay interactive
await page.getByRole('button', { name: '勾画' }).first().click()
await page.waitForTimeout(900)
const canvasBox = await page.locator('canvas.maplibregl-canvas').boundingBox()
if (canvasBox) {
  await page.mouse.click(canvasBox.x + canvasBox.width * 0.35, canvasBox.y + canvasBox.height * 0.35)
  await page.mouse.click(canvasBox.x + canvasBox.width * 0.5, canvasBox.y + canvasBox.height * 0.35)
  await page.mouse.click(canvasBox.x + canvasBox.width * 0.5, canvasBox.y + canvasBox.height * 0.55)
  await page.waitForTimeout(600)
  await shot('22-draw-docked.png')
  const vertices = await page.locator('aside').first().innerText()
  console.log('  editor panel text:', vertices.replace(/\s+/g, ' ').slice(0, 90))
}
await page.getByRole('button', { name: '取消' }).click()

// ---------- admin: region + meteo tabs ----------
await page.evaluate(() => localStorage.clear())
await login('admin', 'admin123')
await page.waitForTimeout(2500)

await page.getByRole('button', { name: '行政区需水' }).click()
await page.waitForTimeout(2500)
await shot('23-admin-regions.png')

const regionInput = page.locator('main input, input[placeholder*="行政区代码"]').first()
if (await regionInput.count()) {
  await regionInput.fill('东营')
  await page.waitForTimeout(1000)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(2500)
  await shot('24-admin-region-summary.png')
}

await page.getByRole('button', { name: '气象数据' }).click()
await page.waitForTimeout(2000)
await shot('25-admin-meteo.png')

const browseBtn = page.getByRole('button', { name: '浏览' }).first()
if (await browseBtn.count()) {
  await browseBtn.click()
  await page.waitForTimeout(1500)
  await shot('26-admin-meteo-fs.png')
}

await browser.close()
console.log('\nconsole errors:', errors.length)
errors.slice(0, 10).forEach((line) => console.log(' -', line.slice(0, 160)))
