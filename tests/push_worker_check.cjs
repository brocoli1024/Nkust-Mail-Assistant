const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('workers/deadline-push/src/index.js','utf8').replace('export default','globalThis.worker =');
const config=JSON.parse(fs.readFileSync('workers/deadline-push/wrangler.jsonc','utf8'));
assert.deepEqual(config.triggers.crons,['*/5 * * * *']);
let calls=[],logs=[];const context={Response,AbortSignal,console:{log(value){logs.push(value);}},fetch:async(url,options)=>{calls.push([url,options]);return new Response('{}',{status:200});}};
vm.runInNewContext(source,context);
(async()=>{assert.equal((await context.worker.fetch()).status,404);await context.worker.scheduled({}, {NKUST_PUSH_TRIGGER_SECRET:'synthetic-secret'},{});
assert.equal(calls.length,1);assert.ok(calls[0][0].endsWith('/internal/push/run'));assert.equal(calls[0][1].method,'POST');assert.equal(calls[0][1].redirect,'manual');assert.equal(calls[0][1].body,'');assert.ok(!source.includes('DATABASE_URL'));for(const status of [302,401,503]){
 logs=[];let bodyRead=false;
 context.fetch=async()=>({ok:false,status,text(){bodyRead=true;throw Error('private-body');}});
 await assert.rejects(context.worker.scheduled({}, {NKUST_PUSH_TRIGGER_SECRET:'synthetic-secret'},{}),/PUSH_TRIGGER_FAILED/);
 assert.ok(logs.includes('PUSH_TRIGGER_HTTP_'+status));assert.equal(bodyRead,false);
 assert.ok(!JSON.stringify(logs).includes('synthetic-secret'));
}
logs=[];context.fetch=async()=>{throw Error('synthetic-secret private provider detail');};
await assert.rejects(context.worker.scheduled({}, {NKUST_PUSH_TRIGGER_SECRET:'synthetic-secret'},{}),/PUSH_TRIGGER_FAILED/);
assert.deepEqual(logs,['PUSH_TRIGGER_FAILED']);
console.log('push worker fixed-target and safe diagnostic contracts passed');})().catch(e=>{console.error(e);process.exitCode=1;});
