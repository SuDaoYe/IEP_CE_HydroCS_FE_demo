/** 验证「需灌水量（净）」与「总水量（毛）」两个口径同时展示。 */
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

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('input[autocomplete="username"]', 'farmer1')
await page.fill('input[autocomplete="current-password"]', '123456')
await page.click('button[type="submit"]')
await page.waitForURL((u) => u.pathname === '/', { timeout: 20000 })
await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 25000 })
await page.waitForTimeout(6000)

// 打开田块详情，切到 30 天 + 周尺度
const card = page.locator('section button').filter({ hasText: '东片一号田' }).first()
await card.click()
await page.waitForTimeout(2800)
await page.getByRole('button', { name: '30 天' }).click()
await page.waitForTimeout(2500)
await shot('50-detail-net-gross.png')

const panel = await page.locator('aside').last().innerText()
const netLine = panel.replace(/\s+/g, ' ').match(/需要灌溉的水量.{0,40}/)
const grossLine = panel.replace(/\s+/g, ' ').match(/总水量（毛.{0,40}/)
console.log('  net card  :', netLine ? netLine[0] : 'not found')
console.log('  gross card:', grossLine ? grossLine[0] : 'not found')

await page.getByRole('button', { name: '周尺度' }).click()
await page.waitForTimeout(900)
await shot('51-weekly-net-gross.png')

// 我的田块页
await page.goto(`${BASE}/fields`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2800)
await shot('52-myfields-net-gross.png')
const fieldsText = await page.locator('body').innerText()
console.log('  myfields has both:', /需灌（净）/.test(fieldsText), /总水量（毛）/.test(fieldsText))

await browser.close()
console.log('\nconsole errors:', errors.length)
errors.slice(0, 8).forEach((line) => console.log(' -', line.slice(0, 150)))
