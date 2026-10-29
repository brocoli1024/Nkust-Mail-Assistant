'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const listeners = [];
let submissions = 0;
const formEvents = {};
const windowEvents = {};
const attributes = {};
const status = { textContent: '', hidden: true };
const form = {
  querySelectorAll(selector) {
    assert.equal(selector, 'select');
    return [
      { addEventListener(type, callback) { assert.equal(type, 'change'); listeners.push(callback); } },
      { addEventListener(type, callback) { assert.equal(type, 'change'); listeners.push(callback); } },
    ];
  },
  requestSubmit() { submissions++; },
  addEventListener(type, callback) { formEvents[type] = callback; },
  setAttribute(key, value) { attributes[key] = value; },
  removeAttribute(key) { delete attributes[key]; },
};
const document = { getElementById(id) {
  if (id === 'filter-status') return status;
  assert.equal(id, 'announcement-filters');
  return form;
} };
const window = { addEventListener(type, callback) { windowEvents[type] = callback; } };
const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'web', 'announcement-filters.js'), 'utf8');
vm.runInNewContext(source, { document, window });
assert.equal(listeners.length, 2, 'both selects must update the results');
listeners[0]();
listeners[1]();
assert.equal(submissions, 2, 'each changed select should submit the GET form');
assert.equal(typeof formEvents.submit, 'function', 'Enter must trigger feedback too');
formEvents.submit();
assert.equal(attributes['aria-busy'], 'true');
assert.equal(status.hidden, false);
assert.match(status.textContent, /正在搜尋/);
assert.equal(form.disabled, undefined, 'GET controls must keep their values');
assert.equal(typeof windowEvents.pageshow, 'function');
windowEvents.pageshow();
assert.equal(attributes['aria-busy'], undefined);
assert.equal(status.hidden, true);
assert.equal(status.textContent, '');
vm.runInNewContext(source, { document: { getElementById() { return null; } }, window });
