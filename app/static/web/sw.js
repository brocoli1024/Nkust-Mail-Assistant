const CACHE_NAME = 'nkust-public-v3';
const PUBLIC_FILES = [
  '/offline',
  '/assets/account.css?v=editorial-1',
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

  if (PUBLIC_FILES.includes(url.pathname + url.search)) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});

function pushPath(payload) {
  if (!payload || typeof payload.path !== 'string') return null;
  if (/^\/public\/(?:announcements|office-mail)\/[1-9][0-9]*$/.test(payload.path)) return payload.path;
  return payload.kind === 'test' && payload.path === '/todos' ? '/todos' : null;
}
self.addEventListener('push', event => {
  let payload;try { payload=event.data?.json(); } catch { return; }
  const path=pushPath(payload);
  if (!path || !/^[a-zA-Z0-9-]{1,64}$/.test(payload.id || '') || typeof payload.title !== 'string' ||
      !Number.isFinite(Date.parse(payload.expires_at)) || Date.parse(payload.expires_at)<=Date.now()) return;
  event.waitUntil(self.registration.showNotification(payload.title.slice(0,120), {
    body:payload.kind==='test'?'這是你主動要求的測試通知。':payload.kind==='review'?'公告內容已變更，請重新核對期限。':'你設定的提醒時間到了，請回公告核對期限。',
    tag:'nkust-reminder-'+payload.id,icon:'/assets/icon-192.png',badge:'/assets/icon-192.png',
    data:{path,kind:payload.kind},renotify:false
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();const path=pushPath(event.notification.data);if(!path)return;
  const target=new URL(path,self.location.origin).href;
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients=>{
    const existing=clients.find(client=>client.url===target);
    if(existing)return existing.focus();return self.clients.openWindow(target);
  }));
});
