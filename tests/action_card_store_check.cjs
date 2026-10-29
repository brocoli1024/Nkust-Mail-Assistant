'use strict';
const assert=require('node:assert/strict');
const {createActionCardStore}=require('../app/static/web/action-card-store.js');
const {validateCorrectionPatch,applyLocalPatch}=require('../app/static/web/action-card.js');
const hash='a'.repeat(64);
const card={source:{kind:'public',source_ref:'synthetic'},baseline_hash:hash,fields:{materials:{value:null,state:'pending'}},requires_action:null,deadline_kind:'unknown'};
const patch={fields:{materials:{mode:'value',value:'在學證明'}}};
function factory(){
  const data=new Map();
  const f={mode:'normal',data,open(){
    const req={};
    queueMicrotask(()=>{req.result={objectStoreNames:{contains:()=>true},close(){},transaction(){
      const tx={error:null,abort(){queueMicrotask(()=>tx.onabort?.());},objectStore(){return {
        get(key){const r={};queueMicrotask(()=>{r.result=structuredClone(data.get(key));r.onsuccess?.();queueMicrotask(()=>{if(!tx.writing)tx.oncomplete?.();});});return r;},
        put(value){tx.writing=true;if(f.mode==='quotaThrow')throw Object.assign(new Error('injected'),{name:'QuotaExceededError'});setTimeout(()=>{if(f.mode==='quota'){tx.error={name:'QuotaExceededError'};tx.onabort?.();}else{data.set(value.source_ref,structuredClone(value));tx.oncomplete?.();}},5);},
        delete(key){tx.writing=true;setTimeout(()=>{data.delete(key);tx.oncomplete?.();},5);}
      };}};return tx;}};req.onsuccess?.();});return req;
  }};return f;
}
(async()=>{
  let opened=false;const denied=createActionCardStore({indexedDB:{open(){opened=true;}}});
  await assert.rejects(denied.commit({card:{source:{kind:'private'}}}),/PRIVATE_SOURCE_NOT_ALLOWED/);assert.equal(opened,false);
  const f=factory(),store=createActionCardStore({indexedDB:f});assert.equal(await store.read('synthetic'),null);
  let done=false;const pending=store.commit({card,patch,operation:'save',expectedRevision:0,now:'2026-10-29T00:00:00Z'}).then(r=>{done=true;return r;});
  await new Promise(r=>setTimeout(r,0));assert.equal(done,false,'wait for transaction commit');
  assert.equal((await pending).revision,1);
  await assert.rejects(store.commit({card,patch,operation:'save',expectedRevision:0}),/REVISION_CONFLICT/);
  f.mode='quota';await assert.rejects(store.commit({card,patch,operation:'save',expectedRevision:1}),/STORAGE_QUOTA/);
  assert.equal((await store.read('synthetic')).revision,1);
  f.mode='quotaThrow';await assert.rejects(store.commit({card,patch,operation:'save',expectedRevision:1}),/STORAGE_QUOTA/);
  assert.equal((await store.read('synthetic')).revision,1);
  f.mode='normal';const newer={...card,baseline_hash:'b'.repeat(64)};
  const r=await store.commit({card:newer,patch,operation:'save',expectedRevision:1});assert.equal(Object.keys(r.baselines).length,2);
  const reset=await store.commit({card:newer,operation:'reset',expectedRevision:2});assert.equal(reset.revisions.length,3);
  assert.equal(applyLocalPatch(card,validateCorrectionPatch(patch)).fields.materials.value,'在學證明');
  assert.throws(()=>validateCorrectionPatch({fields:{deadline:{mode:'value',value:'2026-02-30',confirmed:true}}}));
  assert.throws(()=>validateCorrectionPatch({fields:{summary:{mode:'value',value:'字'.repeat(161)}}}));
  f.data.set('broken',{schema_version:1});await assert.rejects(store.read('broken'),/STORAGE_CORRUPT/);
  await store.erase('synthetic',3);assert.equal(await store.read('synthetic'),null);
  const unicode={...card,source:{...card.source,segments:[{kind:'excerpt',text:'😀在學證明'}]}};
  const evidence=applyLocalPatch(unicode,{fields:{materials:{mode:'value',value:'在學證明',quote:'在學證明'}}}).fields.materials.evidence[0];
  assert.equal(evidence.start,1,'evidence offsets use Unicode code points');
  console.log('Action card store contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
const {formatLocalHistory}=require('../app/static/web/action-card.js');
assert.match(formatLocalHistory({baselines:{old:{source:{segments:[{text:'原始來源A'}]}}},revisions:[]}),/原始來源A/);
