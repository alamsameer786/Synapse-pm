/* ============================================================
   SynapsePM Service Worker
   - Network-first for HTML/API (always fresh data)
   - Cache-first for static assets (fast repeat loads)
   - Offline fallback page when the network is down
   - Never intercepts file downloads or WebSocket upgrades
   ============================================================ */

const CACHE_VERSION = 'synapsepm-v1.0.0';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const PRECACHE_URLS = [
  '/manifest.json',
  '/user/assets/img/logo.png',
  '/offline.html'
];

/* ---------- Install: pre-cache the shell ---------- */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => Promise.allSettled(
        PRECACHE_URLS.map(url =>
          cache.add(new Request(url, { cache: 'reload' }))
            .catch(err => console.warn('[SW] Precache miss:', url, err))
        )
      ))
      .then(() => self.skipWaiting())
  );
});

/* ---------- Activate: clean old caches ---------- */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(k => !k.startsWith(CACHE_VERSION))
          .map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

/* ---------- Fetch handler ---------- */
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Only handle GET requests
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Never touch cross-origin requests (WebSocket, Paddle, CDN, etc.)
  if (url.origin !== self.location.origin) return;

  // Never intercept API calls, auth, uploads or downloads
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/uploads/') ||
    url.pathname.startsWith('/ws') ||
    url.pathname.startsWith('/metrics') ||
    url.pathname.startsWith('/health') ||
    url.pathname.startsWith('/live') ||
    url.pathname.startsWith('/ready') ||
    url.pathname === '/manifest.json' ||
    url.pathname.endsWith('/sw.js')
  ) {
    return; // Let the browser do its normal thing
  }

  // For HTML navigation requests: network-first, offline fallback
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(req)
        .then(resp => {
          const copy = resp.clone();
          caches.open(RUNTIME_CACHE).then(c => c.put(req, copy)).catch(() => {});
          return resp;
        })
        .catch(() =>
          caches.match(req)
            .then(cached => cached || caches.match('/offline.html'))
        )
    );
    return;
  }

  // For static assets: cache-first
  event.respondWith(
    caches.match(req).then(cached => {
      if (cached) return cached;
      return fetch(req)
        .then(resp => {
          // Only cache successful, same-origin, cacheable responses
          if (resp && resp.status === 200 && resp.type === 'basic') {
            const copy = resp.clone();
            caches.open(RUNTIME_CACHE).then(c => c.put(req, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => cached);
    })
  );
});

/* ---------- Allow pages to trigger updates ---------- */
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

/* ---------- Basic push (extensible) ---------- */
self.addEventListener('push', (event) => {
  let data = { title: 'SynapsePM', body: 'You have a new alert.' };
  try { data = { ...data, ...(event.data ? event.data.json() : {}) }; } catch (_) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/user/assets/img/logo.png',
      badge: '/user/assets/img/logo.png',
      data: data.data || {},
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/dashboard.html';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (c.url.includes(url) && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
