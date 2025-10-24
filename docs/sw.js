// =====================================================
// 🚀 USC Streaminginfos Service Worker (Network first)
// =====================================================

const CACHE_NAME = 'usc-streaminginfos-v2';
const OFFLINE_URLS = [
  './',
  './index.html',
  './index_app.html',
  './favicon.png',
  './manifest.webmanifest'
];
const FALLBACK_URL = './index.html';

// -----------------------------------------------------
// Installation: Dateien für Offline-Modus vorcachen
// -----------------------------------------------------
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(OFFLINE_URLS))
      .catch(() => undefined)
  );
});

// -----------------------------------------------------
// Aktivierung: alte Caches löschen + sofort aktiv werden
// -----------------------------------------------------
self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      clients.claim(),
      caches.keys().then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
      )
    ])
  );
});

// -----------------------------------------------------
// Fetch-Handler: Network-first Strategie
// -----------------------------------------------------
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request, { cache: 'no-store' })
      .then((response) => {
        // ✅ Erfolgreich: neue Version ausliefern und Cache aktualisieren
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      })
      .catch(() => {
        // ⚠️ Offline: greife auf Cache oder Fallback zurück
        return caches.match(event.request).then((cached) => cached || caches.match(FALLBACK_URL));
      })
  );
});
