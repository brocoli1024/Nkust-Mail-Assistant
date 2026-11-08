const assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../app/static/web/push-store.js');
assert.equal(typeof api.createPushStore,'function');
for(const name of ['todo-store.js','action-card-store.js','push-store.js']) {
 const s=fs.readFileSync('app/static/web/'+name,'utf8');
 assert.ok(/open\('nkust-campus-assistant',3\)/.test(s),name+' must share v3');
 assert.ok(s.includes('pushBindings')&&s.includes('pushOutbox'));
}
const todo=fs.readFileSync('app/static/web/todo-store.js','utf8');assert.ok(todo.includes('queueCancellation'));
console.log('push store schema and public API contracts passed; native IDB harness required separately');
