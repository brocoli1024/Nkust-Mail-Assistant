const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('workers/deadline-push/src/index.js','utf8').replace('export default','globalThis.worker =');
const config=JSON.parse(fs.readFileSync('workers/deadline-push/wrangler.jsonc','utf8'));
assert.deepEqual(config.triggers.crons,['*/5 * * * *']);
let calls=[];const context={Response,AbortSignal,console:{log(){}},fetch:async(url,options)=>{calls.push([url,options]);return new Response('{}',{status:200});}};
vm.runInNewContext(source,context);
(async()=>{assert.equal((await context.worker.fetch()).status,404);await context.worker.scheduled({}, {NKUST_PUSH_TRIGGER_SECRET:'synthetic-secret'},{});
assert.equal(calls.length,1);assert.ok(calls[0][0].endsWith('/internal/push/run'));assert.equal(calls[0][1].method,'POST');assert.equal(calls[0][1].redirect,'error');assert.equal(calls[0][1].body,'');assert.ok(!source.includes('DATABASE_URL'));console.log('push worker fixed-target contracts passed');})().catch(e=>{console.error(e);process.exitCode=1;});
