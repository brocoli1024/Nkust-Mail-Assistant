'use strict';
document.getElementById('run').addEventListener('click',async()=>{
 const out=document.getElementById('result');out.textContent='測試中';const name='nkust-todo-qa-'+crypto.randomUUID(),key='qa',hash='a'.repeat(64);
 const card={source:{kind:'public',source_ref:key,title:'合成驗收',segments:[],url:null},fields:{deadline:{value:null,state:'pending'}},baseline_hash:hash};
 const factory={open:(_name,version)=>indexedDB.open(name,version)};
 const assert=(ok,text)=>{if(!ok)throw Error(text);};
 function faultFactory(mode){return {open(_name,version){const outer={},request=indexedDB.open(name,version);request.onerror=()=>outer.onerror?.();request.onsuccess=()=>{const actual=request.result;outer.result={close:()=>actual.close(),transaction(...args){const tx=actual.transaction(...args),original=tx.objectStore.bind(tx);tx.objectStore=n=>new Proxy(original(n),{get(target,key){if(key==='put')return v=>{if(mode==='quota')throw new DOMException('injected','QuotaExceededError');const r=target.put(v);r.onsuccess=()=>tx.abort();return r;};const v=target[key];return typeof v==='function'?v.bind(target):v;}});return tx;}};outer.onsuccess?.();};return outer;}};}
 try{
  await new Promise((resolve,reject)=>{const req=indexedDB.open(name,1);req.onupgradeneeded=()=>req.result.createObjectStore('publicActionCards',{keyPath:'source_ref'});req.onerror=reject;req.onsuccess=()=>{const db=req.result,tx=db.transaction('publicActionCards','readwrite');tx.objectStore('publicActionCards').put({schema_version:1,source_ref:key,revision:1,baselines:{[hash]:card},revisions:[{revision:1,baseline_hash:hash,operation:'reset',patch:{fields:{}}}]});tx.oncomplete=()=>{db.close();resolve();};};});
  const store=NkustTodos.createTodoStore({indexedDB:factory});await store.change({operation:'add',card,sourceRef:key,expectedRevision:0});
  const old=await NkustActionCardStore.createActionCardStore({indexedDB:factory}).read(key);assert(old.revision===1,'v1修正必須保留');
  assert((await NkustTodos.createTodoStore({indexedDB:factory}).readAll())[0].revision===1,'重開保留');
  const result=await Promise.allSettled(['complete','snooze'].map(operation=>store.change({operation,sourceRef:key,expectedRevision:1})));assert(result.filter(r=>r.status==='fulfilled').length===1,'競爭只可一方成功');
  for(const mode of ['quota','abort']){let rejected=false;try{await NkustTodos.createTodoStore({indexedDB:faultFactory(mode)}).change({operation:'complete',sourceRef:key,expectedRevision:2});}catch{rejected=true;}assert(rejected,'故障不能成功');assert((await store.readAll())[0].revision===2,'故障不得改舊值');}
  const r=await store.change({operation:'snooze',sourceRef:key,expectedRevision:2,now:'2026-10-29T16:00:00Z'});assert(NkustTodos.projectTodo(r,r.snoozed_until).effective_status==='active','稍後到期重新出現');
  await store.change({operation:'remove',sourceRef:key,expectedRevision:3});await store.change({operation:'add',card,sourceRef:key,expectedRevision:4});
  out.textContent='PASS：原生 v1→v2 保留修正、待辦重開保存、雙寫入衝突、quota/abort 故障注入、稍後到期、移除重加均通過。';
 }catch(e){out.textContent='FAIL：'+e.message;}finally{indexedDB.deleteDatabase(name);}
});
