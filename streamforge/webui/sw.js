// Minimal service worker so the app can be "Add to Home Screen" as a PWA.
const CACHE = "streamforge-v1";
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  // Never cache API calls; only cache the shell for offline launch.
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) return;
  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(event.request).then(
        (hit) =>
          hit ||
          fetch(event.request).then((resp) => {
            cache.put(event.request, resp.clone());
            return resp;
          })
      )
    )
  );
});
