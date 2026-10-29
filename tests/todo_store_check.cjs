'use strict';
const assert=require('node:assert/strict');
const {createTodoStore,nextSnooze,projectTodo}=require('../app/static/web/todo-store.js');
const now='2026-10-29T16:00:00Z';
const card={source:{kind:'public',source_ref:'synthetic',title:'合成待辦',segments:[],url:null},baseline_hash:'a'.repeat(64),fields:{deadline:{value:null,state:'pending'}}};
function factory(){
 const data=new Map();let tail=Promise.resolve();const f={data,mode:'normal',open(name,version){assert.equal(version,2);const req={};queueMicrotask(()=>{req.result={objectStoreNames:{contains:()=>true},close(){},transaction(){
 let release;const previous=tail;tail=new Promise(r=>release=r);let aborted=false,pending=null;const tx={error:null,abort(){aborted=true;queueMicrotask(()=>{tx.onabort?.();release();});},objectStore(){return {
 get(key){const r={};previous.then(()=>queueMicrotask(()=>{r.result=structuredClone(data.get(key));r.onsuccess?.();if(!pending&&!aborted){tx.oncomplete?.();release();}}));return r;},
 getAll(){const r={};previous.then(()=>queueMicrotask(()=>{r.result=structuredClone([...data.values()]);r.onsuccess?.();tx.oncomplete?.();release();}));return r;},
 put(value){pending=value;if(f.mode==='quota')throw Object.assign(Error('quota'),{name:'QuotaExceededError'});setTimeout(()=>{if(aborted)return;if(f.mode==='abort'){tx.abort();return;}data.set(value.source_ref,structuredClone(value));tx.oncomplete?.();release();},5);}
 };}};return tx;}};req.onsuccess?.();});return req;}};return f;
}
(async()=>{
 assert.equal(nextSnooze(now),'2026-10-31T01:00:00.000Z');
 assert.equal(nextSnooze('2026-12-31T16:00:00Z'),'2027-01-02T01:00:00.000Z');
 let opened=false;await assert.rejects(createTodoStore({indexedDB:{open(){opened=true;}}}).change({operation:'add',card:{source:{kind:'private'}}}),/PRIVATE_SOURCE/);assert.equal(opened,false);
 const f=factory(),store=createTodoStore({indexedDB:f});assert.deepEqual(await store.readAll(),[]);
 let completed=false;const adding=store.change({operation:'add',card,sourceRef:'synthetic',expectedRevision:0,now}).then(r=>{completed=true;return r;});await new Promise(r=>setTimeout(r,0));assert.equal(completed,false);let r=await adding;assert.equal(r.revision,1);
 const races=await Promise.allSettled(['complete','snooze'].map(operation=>store.change({operation,sourceRef:'synthetic',expectedRevision:1,now})));assert.equal(races.filter(r=>r.status==='fulfilled').length,1);
 for(const mode of ['quota','abort']){f.mode=mode;await assert.rejects(store.change({operation:'complete',sourceRef:'synthetic',expectedRevision:2,now}));assert.equal((await store.readAll())[0].revision,2);}f.mode='normal';
 await store.change({operation:'remove',sourceRef:'synthetic',expectedRevision:2,now});r=await store.change({operation:'add',card,sourceRef:'synthetic',expectedRevision:3,now});assert.equal(r.revision,4);await assert.rejects(store.change({operation:'complete',sourceRef:'synthetic',expectedRevision:1,now}),/REVISION_CONFLICT/);
 r=await store.change({operation:'snooze',sourceRef:'synthetic',expectedRevision:4,now});assert.equal(projectTodo(r,now).effective_status,'snoozed');assert.equal(projectTodo(r,r.snoozed_until).effective_status,'active');
 r.card.fields.deadline={value:'2026-10-29',state:'user_confirmed'};assert.equal(projectTodo(r,now).deadline_group,'overdue');r.card.fields.deadline.state='pending';assert.equal(projectTodo(r,now).deadline_group,'none');
 f.data.set('synthetic',{...r,card:{source:{kind:'private'}}});await assert.rejects(store.readAll(),/STORAGE_CORRUPT/);
 console.log('Todo store contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
