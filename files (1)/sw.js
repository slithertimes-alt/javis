// Minimal service worker — just enough to satisfy PWA installability requirements.
// It caches the app shell so JARVIS still opens (UI-only, no AI replies) if you're offline.

const CACHE_NAME = 'jarvis-shell-v1';
const APP_SHELL = ['./jarvis.html', './manifest.json', './icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network-first for API calls (never serve stale AI responses from cache)
  if (event.request.url.includes('api.anthropic.com') || event.request.url.includes('api.groq.com')) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
