'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const listeners = [];
let submissions = 0;
const form = {
  querySelectorAll(selector) {
    assert.equal(selector, 'select');
    return [
      { addEventListener(type, callback) { assert.equal(type, 'change'); listeners.push(callback); } },
      { addEventListener(type, callback) { assert.equal(type, 'change'); listeners.push(callback); } },
    ];
  },
  requestSubmit() { submissions++; },
};
const document = { getElementById(id) {
  assert.equal(id, 'announcement-filters');
  return form;
} };
const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'web', 'announcement-filters.js'), 'utf8');
vm.runInNewContext(source, { document });
assert.equal(listeners.length, 2, 'both selects must update the results');
listeners[0]();
listeners[1]();
assert.equal(submissions, 2, 'each changed select should submit the GET form');
