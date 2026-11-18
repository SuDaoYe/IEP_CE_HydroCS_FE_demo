/** Captures the admin overview (service status incl. ET model) for the README. */
import { chromium } from 'playwright'
import path from 'node:path'

const OUT = path.resolve('..', '.scratch')
const BASE = 'http://127.0.0.1:8000'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1280, height: 760 }, deviceScaleFactor: 2 })
const page = await context.newPage()

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('input[name="username"], input[autocomplete="username"]', 'admin')
await page.fill('input[type="password"]', 'admin123')
await page.click('button[type="submit"]')
await page.waitForURL(/\/admin/, { timeout: 30000 })
await page.waitForTimeout(6500)

await page.screenshot({ path: path.join(OUT, '61-admin-overview.png') })
console.log('shot overview')

// 用户与田块 页签（README 的「管理后台」整页截图）
await page.getByRole('button', { name: '用户与田块' }).first().click()
await page.waitForTimeout(3500)
await page.screenshot({ path: path.join(OUT, '62-admin-users.png') })
console.log('shot users tab')

await browser.close()
