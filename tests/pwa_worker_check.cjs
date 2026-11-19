// Exercise the service worker without a browser or any account data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'web', 'sw.js'), 'utf8');
const handlers = {};
const cached = new Map();
let added = [];
let networkOnline = true;
const origin = 'https://example.test';
const cache = {
  addAll: async urls => {
    added = [...urls];
    for (const url of urls) cached.set(origin + url, { kind: 'public', url });
  },
  match: async request => cached.get(typeof request === 'string' ? origin + request : request.url),
};
const caches = {
  open: async () => cache,
  keys: async () => ['nkust-public-v3'],
  delete: async () => true,
  match: cache.match,
};
const self = {
  location: { origin },
  addEventListener: (name, handler) => { handlers[name] = handler; },
  skipWaiting: async () => {},
  clients: { claim: async () => {} },
};
const fetch = async request => {
  if (!networkOnline) throw new Error('offline');
  return { kind: 'network', url: request.url };
};
vm.runInNewContext(source, { self, caches, fetch, URL, Promise });

async function dispatch(name, request) {
  let response;
  let task;
  handlers[name]({
    request,
    respondWith: value => { response = value; },
    waitUntil: value => { task = value; },
  });
  if (task) await task;
  return response === undefined ? undefined : await response;
}

const request = (url, method = 'GET', mode = 'navigate') =>
  ({ url: origin + url, method, mode });

(async () => {
  await dispatch('install');
  assert.deepEqual(added.sort(), [
    '/offline', '/assets/account.css?v=editorial-1', '/assets/fonts/Manrope.ttf', '/assets/icon.svg', '/assets/icon-192.png',
    '/assets/icon-512.png', '/assets/apple-touch-icon.png',
  ].sort());
  assert.equal(cached.size, 7);

  for (const url of ['/dashboard', '/settings', '/announcements', '/announcements/123']) {
    const response = await dispatch('fetch', request(url));
    assert.equal(response.kind, 'network');
    assert.equal(cached.size, 7);
  }
  assert.equal(await dispatch('fetch', request('/auth/google/callback?code=secret')), undefined);
  assert.equal(await dispatch('fetch', request('/sync', 'POST')), undefined);
  assert.equal(await dispatch('fetch', request('/api/me', 'GET', 'cors')), undefined);
  for (const url of ['/demo', '/demo/announcements/demo-event', '/public/announcements', '/public/announcements/1']) {
    assert.equal(await dispatch('fetch', request(url)), undefined, 'public/demo HTML must not enter Cache Storage');
    assert.equal(cached.size, 7);
  }

  networkOnline = false;
  const offline = await dispatch('fetch', request('/dashboard'));
  assert.equal(offline.kind, 'public');
  assert.equal(offline.url, '/offline');
  assert.equal(cached.size, 7);
  assert.equal((await dispatch('fetch', request('/assets/account.css?v=editorial-1', 'GET', 'no-cors'))).kind, 'public');
})().catch(error => { console.error(error); process.exitCode = 1; });

// Visible notification and safe click contracts, separate from existing cache tests.
(async()=>{
 let displayed=[],opened=[];self.registration={showNotification:async(title,options)=>displayed.push([title,options])};
 self.clients.matchAll=async()=>[];self.clients.openWindow=async path=>opened.push(path);
 async function push(payload){let pending;handlers.push({data:{json:()=>payload},waitUntil:p=>pending=p});await pending;}
 await push({id:'synthetic',title:'合成截止提醒',path:'/public/office-mail/1',expires_at:new Date(Date.now()+60000).toISOString(),kind:'deadline'});
 assert.equal(displayed.length,1);assert.equal(displayed[0][1].tag,'nkust-reminder-synthetic');
 let pending;handlers.notificationclick({notification:{data:displayed[0][1].data,close(){}},waitUntil:p=>pending=p});await pending;
 assert.equal(opened[0],origin+'/public/office-mail/1');
 await push({id:'bad',title:'x',path:'https://evil.invalid',expires_at:new Date(Date.now()+60000).toISOString()});
 await push({id:'expired',title:'x',path:'/public/announcements/1',expires_at:'2000-01-01T00:00:00Z'});
 assert.equal(displayed.length,1);console.log('visible push and safe click contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
