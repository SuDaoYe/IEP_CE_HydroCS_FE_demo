import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('.scratch')
fs.mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8000'

const errors = []

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false })
  console.log('  shot:', name)
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 15000 })
  await page.fill('input[autocomplete="username"]', 'farmer1')
  await page.fill('input[autocomplete="current-password"]', '123456')
  await page.click('button[type="submit"]')
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 })
  console.log('  logged in →', new URL(page.url()).pathname)
}

async function waitMap(page) {
  await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 25000 })
  await page.waitForTimeout(7000) // tiles
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })

// ---------- desktop ----------
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await context.newPage()
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`[desktop] ${msg.text()}`)
  })
  page.on('pageerror', (err) => errors.push(`[desktop pageerror] ${err.message}`))

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  await shot(page, '01-login-desktop.png')

  await login(page)
  await waitMap(page)
  await shot(page, '02-workspace-desktop.png')

  // recognition flow
  const recognize = page.getByRole('button', { name: '识别' }).first()
  if (await recognize.count()) {
    await recognize.click()
    await page.waitForTimeout(14000)
    await shot(page, '02b-recognize-desktop.png')
  }

  const fieldCard = page.locator('section button').filter({ hasText: '东片一号田' }).first()
  if (await fieldCard.count()) {
    await fieldCard.click()
    await page.waitForTimeout(3200)
    await shot(page, '03-detail-desktop.png')
  } else {
    console.log('  !! field card not found')
  }

  await page.goto(`${BASE}/fields`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  await shot(page, '04-myfields-desktop.png')

  await page.goto(`${BASE}/history`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  await shot(page, '05-history-desktop.png')

  await context.close()
}

// ---------- mobile ----------
{
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  })
  const page = await context.newPage()
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`[mobile] ${msg.text()}`)
  })
  page.on('pageerror', (err) => errors.push(`[mobile pageerror] ${err.message}`))

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1000)
  await shot(page, '06-login-mobile.png')

  await login(page)
  await waitMap(page)
  await shot(page, '07-workspace-mobile.png')

  const card = page.locator('section button').filter({ hasText: '东片一号田' }).first()
  if (await card.count()) {
    await card.click()
    await page.waitForTimeout(3200)
    await shot(page, '08-detail-mobile.png')
  } else {
    console.log('  !! mobile field card not found')
  }

  await page.goto(`${BASE}/fields`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2200)
  await shot(page, '09-myfields-mobile.png')
  await context.close()
}

// ---------- admin ----------
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await context.newPage()
  page.on('pageerror', (err) => errors.push(`[admin pageerror] ${err.message}`))
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[autocomplete="username"]')
  await page.fill('input[autocomplete="username"]', 'admin')
  await page.fill('input[autocomplete="current-password"]', 'admin123')
  await page.click('button[type="submit"]')
  await page.waitForURL((url) => url.pathname.startsWith('/admin'), { timeout: 20000 })
  await page.waitForTimeout(3000)
  await shot(page, '10-admin-desktop.png')
  await context.close()
}

await browser.close()

console.log('\nconsole errors:', errors.length)
for (const line of errors.slice(0, 20)) console.log(' -', line)
