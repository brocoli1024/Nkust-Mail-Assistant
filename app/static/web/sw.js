const CACHE_NAME = 'nkust-public-v2';
const PUBLIC_FILES = [
  '/offline',
  '/assets/account.css',
  '/assets/fonts/Manrope.ttf',
  '/assets/icon.svg',
  '/assets/icon-192.png',
  '/assets/icon-512.png',
  '/assets/apple-touch-icon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PUBLIC_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(names => Promise.all(
      names.filter(name => name.startsWith('nkust-public-') && name !== CACHE_NAME)
        .map(name => caches.delete(name))
    )).then(() => self.clients.claim())
  );
});

function isAppPage(path) {
  return path === '/' || path === '/login' || path === '/dashboard' ||
    path === '/settings' || path === '/announcements' ||
    /^\/announcements\/\d+$/.test(path);
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    if (isAppPage(url.pathname)) {
      // Never put account pages, announcements, or OAuth data in Cache Storage.
      event.respondWith(fetch(request).catch(() => caches.match('/offline')));
    }
    return;
  }

  if (PUBLIC_FILES.includes(url.pathname)) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});
