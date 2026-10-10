// Sideline service worker: caches the app shell so it opens offline.
// ESPN data is cached by the app itself in localStorage, not here.
const VERSION = 'sideline-v3';
const SHELL = ['./', './index.html', './styles.css', './app.js', './feed.js', './accounts.json', './manifest.webmanifest', './icons/icon.svg', './icons/icon-180.png', './icons/icon-512.png'];
const MEDIA = /\.(mp3|m4a|aac|wav|ogg|mp4|webm|mov)$/i; // never cached: audio and video would fill storage

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return; // let ESPN calls go straight to the network
  if (MEDIA.test(url.pathname) || event.request.headers.has('range')) return; // media streams straight from the network
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match('./index.html')))
  );
});
