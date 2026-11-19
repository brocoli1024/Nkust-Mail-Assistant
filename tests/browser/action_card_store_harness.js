'use strict';
document.getElementById('run').addEventListener('click',async()=>{
const output=document.getElementById('result');output.textContent='測試中';
const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
const key='qa:'+crypto.randomUUID(),fields=Object.fromEntries(['summary','action','audience','materials','deadline','event_date'].map(k=>[k,{value:null,state:'pending'}]));
const card={source:{kind:'public',source_ref:key,segments:[]},fields,baseline_hash:'a'.repeat(64)},patch={fields:{materials:{mode:'value',value:'合成材料'}}};
const store=NkustActionCardStore.createActionCardStore();
function faultFactory(mode){return {open(name,version){
  const outer={},request=indexedDB.open(name,version);
  request.onupgradeneeded=()=>{outer.result=request.result;outer.onupgradeneeded?.();};
  request.onerror=()=>outer.onerror?.();
  request.onsuccess=()=>{const actual=request.result;outer.result={objectStoreNames:actual.objectStoreNames,close:()=>actual.close(),transaction(...args){const tx=actual.transaction(...args),original=tx.objectStore.bind(tx);tx.objectStore=(name)=>{const records=original(name);return new Proxy(records,{get(target,key){if(key==='put')return value=>{if(mode==='quota')throw new DOMException('Injected quota','QuotaExceededError');const req=target.put(value);req.onsuccess=()=>tx.abort();return req;};const v=target[key];return typeof v==='function'?v.bind(target):v;}});};return tx;}};outer.onsuccess?.();};return outer;
}};}
try{
  assert(await store.read(key)===null,'初始不應有資料');
  await store.commit({card,patch,operation:'save',expectedRevision:0});
  assert((await NkustActionCardStore.createActionCardStore().read(key)).revision===1,'重開仍須保存');
  const result=await Promise.allSettled([store.commit({card,patch,operation:'save',expectedRevision:1}),store.commit({card,patch,operation:'save',expectedRevision:1})]);
  assert(result.filter(x=>x.status==='fulfilled').length===1,'同版本競爭只能一方成功');
  for(const mode of ['quota','abort']){
    const faulty=NkustActionCardStore.createActionCardStore({indexedDB:faultFactory(mode)});
    let rejected=false;try{await faulty.commit({card,patch,operation:'save',expectedRevision:2});}catch{rejected=true;}
    assert(rejected,'故障應回報失敗');assert((await store.read(key)).revision===2,'故障不得覆寫先前版本');
  }
  const newer={...card,baseline_hash:'b'.repeat(64)};
  await store.commit({card:newer,operation:'reset',expectedRevision:2});
  const saved=await store.read(key);assert(saved.revisions.length===3&&Object.keys(saved.baselines).length===2,'重設須保留歷史與舊快照');
  await store.erase(key,3);output.textContent='PASS：原生交易保存、重開、同版本競爭、quota/abort 故障注入、重設歷史均通過。';
}catch(e){output.textContent='FAIL：'+e.message;}
});
