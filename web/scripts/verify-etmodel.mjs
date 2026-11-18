/** Verifies the ET prediction model is surfaced in the admin overview. */
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('..', '.scratch')
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

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('input[name="username"], input[autocomplete="username"]', 'admin')
await page.fill('input[type="password"]', 'admin123')
await page.click('button[type="submit"]')
await page.waitForURL(/\/admin/, { timeout: 30000 })
await page.waitForTimeout(6000)

const text = await page.evaluate(() => document.body.innerText)
const hasModel = text.includes('ET 预测模型')
const hasWindow = /30 天窗口/.test(text)
const hasMetrics = /RMSE/.test(text) && /R²/.test(text)
console.log('overview has model row:', hasModel, '| window:', hasWindow, '| metrics:', hasMetrics)

const line = text
  .split('\n')
  .map((s) => s.trim())
  .filter((s) => s.includes('ET 预测模型') || s.includes('训练') || s.includes('RMSE'))
  .slice(0, 4)
console.log('snippets:', JSON.stringify(line, null, 0))

await page.screenshot({ path: path.join(OUT, '60-admin-etmodel.png'), fullPage: true })
console.log('  shot: 60-admin-etmodel.png')
console.log('console errors:', errors.length)
if (errors.length) console.log(errors.slice(0, 5).join('\n'))

await browser.close()
process.exit(hasModel && hasWindow && errors.length === 0 ? 0 : 1)
