const cacheName = "omi-v5-pwa-v1";
const shell = ["/", "/manifest.webmanifest", "/omi-mark.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    fetch("/").then(async (response) => {
      if (!response.ok) throw new Error("PWA shell is unavailable");
      const html = await response.clone().text();
      const assets = Array.from(
        html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g),
        (match) => match[1]
      );
      const cache = await caches.open(cacheName);
      await cache.put("/", response);
      await cache.addAll([...shell.slice(1), ...new Set(assets)]);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter(
              (name) => name.startsWith("omi-v5-pwa-") && name !== cacheName
            )
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/v1/") ||
    url.pathname.startsWith("/__omi/api/")
  ) {
    return;
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(cacheName).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          request.mode === "navigate"
            ? caches.match("/")
            : Promise.reject(new Error("PWA resource is unavailable offline"))
        );
    })
  );
});
