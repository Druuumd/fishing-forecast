/* KVH Forecast service worker.
 *
 * Two responsibilities:
 *   1. Web Push delivery (notification on push event, click handler).
 *   2. Offline-fallback caching so that anglers on the lake without
 *      mobile data still see the LAST KNOWN forecast/history.
 *
 * Cache strategy:
 *   - Static assets (JS bundle, CSS, HTML, favicons): cache-first with
 *     background revalidation. Vite emits hashed filenames so old
 *     bundles age out naturally; index.html is short-TTL because it
 *     pins the current bundle hash.
 *   - Whitelisted GET API endpoints (forecast, history, vapid pubkey,
 *     condition catalog, health/ready): network-first with cache
 *     fallback. When online → fresh data. When offline → most recent
 *     successful response.
 *   - All other requests (POST, auth, admin, push subscribe, catch
 *     submission): bypass the SW, go straight to network.
 *
 * Cache versioning:
 *   - All caches are prefixed with CACHE_VERSION. Bumping the version
 *     causes the activate handler to drop every previous cache.
 *   - Bump CACHE_VERSION when the cached payload shape changes in a
 *     non-backward-compatible way.
 */

const CACHE_VERSION = "kvh-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const API_CACHE = `${CACHE_VERSION}-api`;

// API endpoints that benefit from offline cache. Exact path or prefix.
const API_CACHEABLE = [
  "/v1/forecast",          // prefix (handles ?species=&zone=)
  "/v1/water-level/history",
  "/v1/weather/history",
  "/v1/push/vapid-public-key",
  "/v1/push/condition-types",
  "/v1/legal/info",
  "/v1/health",
  "/v1/ready",
];

function isApiCacheable(path) {
  return API_CACHEABLE.some((p) => path === p || path.startsWith(`${p}?`));
}

// ---- Lifecycle -----------------------------------------------------------

self.addEventListener("install", (event) => {
  // Don't pre-fetch the app shell here — we don't know the hashed asset
  // names ahead of time. The first navigation populates the cache.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => !k.startsWith(CACHE_VERSION))
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ---- Fetch routing -------------------------------------------------------

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // API: only same-origin, only whitelisted paths.
  if (url.origin === self.location.origin && url.pathname.startsWith("/v1/")) {
    if (isApiCacheable(url.pathname)) {
      event.respondWith(networkFirst(req, API_CACHE));
    }
    return; // non-cacheable /v1/* (POST/auth/admin/etc.) bypass SW
  }

  // Same-origin static assets (HTML, CSS, JS, images).
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(req, STATIC_CACHE));
  }
});

async function networkFirst(req, cacheName) {
  try {
    const fresh = await fetch(req);
    if (fresh && fresh.ok) {
      const cache = await caches.open(cacheName);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const cached = await caches.match(req);
    if (cached) return cached;
    // Synthesise a sensible offline response so the app can show a
    // friendly state rather than a generic fetch failure.
    return new Response(
      JSON.stringify({
        error: {
          code: "OFFLINE_NO_CACHE",
          message: "Нет сети и нет сохранённого ответа.",
          retryable: true,
        },
      }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function cacheFirst(req, cacheName) {
  const cached = await caches.match(req);
  if (cached) {
    // Background revalidation — don't await, let it update next request.
    fetch(req)
      .then((fresh) => {
        if (fresh && fresh.ok) {
          caches.open(cacheName).then((c) => c.put(req, fresh));
        }
      })
      .catch(() => {});
    return cached;
  }
  try {
    const fresh = await fetch(req);
    if (fresh && fresh.ok) {
      const cache = await caches.open(cacheName);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch (err) {
    // No cached copy and we're offline — for HTML navigations, fall
    // back to the cached "/" so the SPA still loads (it can then show
    // its own offline state for any unavailable data).
    if (req.mode === "navigate") {
      const root = await caches.match("/");
      if (root) return root;
    }
    return new Response("Offline", { status: 503 });
  }
}

// ---- Web Push ------------------------------------------------------------

self.addEventListener("push", (event) => {
  let payload = { title: "KVH Forecast", body: "Новый прогноз клёва" };
  if (event.data) {
    try {
      payload = { ...payload, ...event.data.json() };
    } catch (_) {
      payload.body = event.data.text();
    }
  }
  const options = {
    body: payload.body,
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    tag: payload.data?.date || "kvh-default",
    renotify: true,
    data: payload.data || {},
  };
  event.waitUntil(self.registration.showNotification(payload.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url.includes(self.location.origin)) {
          w.focus();
          return;
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
