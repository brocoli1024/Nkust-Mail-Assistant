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
  keys: async () => ['nkust-public-v2'],
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
    '/offline', '/assets/account.css', '/assets/fonts/Manrope.ttf', '/assets/icon.svg', '/assets/icon-192.png',
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

  networkOnline = false;
  const offline = await dispatch('fetch', request('/dashboard'));
  assert.equal(offline.kind, 'public');
  assert.equal(offline.url, '/offline');
  assert.equal(cached.size, 7);
  assert.equal((await dispatch('fetch', request('/assets/account.css', 'GET', 'no-cors'))).kind, 'public');
})().catch(error => { console.error(error); process.exitCode = 1; });
