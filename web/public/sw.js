/* HydroCS service worker — app shell cache + imagery tile cache.
 *
 * Strategy per request class:
 *   navigation  → network first, fall back to the cached shell (offline start)
 *   /assets/*   → cache first (hashed filenames never change)
 *   /api/*      → network only; the app keeps its own IndexedDB copy
 *   tiles       → stale-while-revalidate, capped cache
 */

const SHELL_CACHE = 'hydrocs-shell-v1'
const TILE_CACHE = 'hydrocs-tiles-v1'
const TILE_LIMIT = 220

const SHELL_ASSETS = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg']

/** Cache the shell plus the hashed bundles index.html points at. */
async function precacheShell() {
  const cache = await caches.open(SHELL_CACHE)
  await Promise.allSettled(SHELL_ASSETS.map((asset) => cache.add(asset)))
  try {
    const response = await fetch('/index.html', { cache: 'no-store' })
    const html = await response.text()
    const bundles = [...html.matchAll(/(\/assets\/[A-Za-z0-9._-]+)/g)].map((match) => match[1])
    await Promise.allSettled(bundles.map((url) => cache.add(url)))
  } catch {
    /* offline during install — the runtime cache will fill in later */
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    await precacheShell()
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((key) => key !== SHELL_CACHE && key !== TILE_CACHE).map((key) => caches.delete(key)))
      await self.clients.claim()
      await precacheShell()
    })(),
  )
})

async function trimCache(name, limit) {
  const cache = await caches.open(name)
  const keys = await cache.keys()
  if (keys.length <= limit) return
  for (const key of keys.slice(0, keys.length - limit)) await cache.delete(key)
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request)
          const cache = await caches.open(SHELL_CACHE)
          cache.put('/index.html', response.clone())
          return response
        } catch {
          const cache = await caches.open(SHELL_CACHE)
          return (await cache.match('/index.html')) ?? Response.error()
        }
      })(),
    )
    return
  }

  if (url.pathname.startsWith('/api/v1/imagery/tiles/')) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(TILE_CACHE)
        const cached = await cache.match(request)
        const network = fetch(request)
          .then((response) => {
            if (response.ok) {
              cache.put(request, response.clone())
              void trimCache(TILE_CACHE, TILE_LIMIT)
            }
            return response
          })
          .catch(() => undefined)
        return cached ?? (await network) ?? Response.error()
      })(),
    )
    return
  }

  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(SHELL_CACHE)
        const cached = await cache.match(request)
        if (cached) return cached
        const response = await fetch(request)
        if (response.ok) cache.put(request, response.clone())
        return response
      })(),
    )
  }
})
