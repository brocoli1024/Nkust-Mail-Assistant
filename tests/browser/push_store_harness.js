document.getElementById('run').addEventListener('click',async()=>{
 const out=document.getElementById('result');out.textContent='測試中';const name='nkust-push-qa-'+crypto.randomUUID(),key='qa-public';
 const hash='a'.repeat(64),card={source:{kind:'public',source_ref:key,title:'合成通知驗收'},fields:{deadline:{value:null,state:'pending'}},baseline_hash:hash};
 const factory={open:(_name,version)=>indexedDB.open(name,version)};
 const assert=(ok,text)=>{if(!ok)throw Error(text);};
 const call=fn=>new Promise((resolve,reject)=>{const r=indexedDB.open(name,3);r.onerror=reject;r.onsuccess=()=>{const db=r.result;Promise.resolve(fn(db)).then(resolve,reject).finally(()=>db.close());};});
 const records=store=>call(db=>new Promise((resolve,reject)=>{const tx=db.transaction(store),r=tx.objectStore(store).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=reject;}));
 function faultFactory(){return {open(_name,version){const outer={},r=indexedDB.open(name,version);r.onerror=()=>outer.onerror?.();r.onsuccess=()=>{const db=r.result;outer.result={close:()=>db.close(),transaction(...args){const tx=db.transaction(...args),original=tx.objectStore.bind(tx);tx.objectStore=n=>new Proxy(original(n),{get(target,k){if(k==='put'&&n==='pushOutbox')return()=>{tx.abort();throw new Error('injected abort');};const v=target[k];return typeof v==='function'?v.bind(target):v;}});return tx;}};outer.onsuccess?.();};return outer;}};}
 try{
  await new Promise((resolve,reject)=>{const r=indexedDB.open(name,2);r.onupgradeneeded=()=>{r.result.createObjectStore('publicActionCards',{keyPath:'source_ref'});r.result.createObjectStore('publicTodos',{keyPath:'source_ref'});};r.onerror=reject;r.onsuccess=()=>{const db=r.result,tx=db.transaction('publicActionCards','readwrite');tx.objectStore('publicActionCards').put({source_ref:key,marker:'legacy'});tx.oncomplete=()=>{db.close();resolve();};};});
  const todos=NkustTodos.createTodoStore({indexedDB:factory}),push=NkustPushStore.createPushStore({indexedDB:factory});
  await todos.change({operation:'add',card,sourceRef:key,expectedRevision:0});
  assert((await records('publicActionCards'))[0].marker==='legacy','v2→v3保留原資料');
  assert((await records('pushOutbox')).length===0,'未opt-in不上傳');
  await push.setDevice({epoch:'epoch-A'});
  await push.setIntent({sourceRef:key,expectedRevision:1,intent:{enabled:true,source_version:hash,deadline:{kind:'date',value:'2026-12-01',confirmed:true,basis:'user'},remind_at:'2026-11-30T01:00:00Z'}});
  let calls=0;
  const api={list:async()=>({device:{epoch:'epoch-A'},items:[]}),save:async item=>{calls++;return {server_revision:1,client_revision:item.intent.client_revision,status:'pending'};}};
  await push.flush({api,epoch:'epoch-A'});assert(calls===1,'明確啟用才同步');
  let rejected=false;try{await NkustTodos.createTodoStore({indexedDB:faultFactory()}).change({operation:'complete',sourceRef:key,expectedRevision:1});}catch{rejected=true;}
  assert(rejected&&(await todos.readAll())[0].status==='active','取消佇列故障時待辦同交易撤回');
  assert((await records('pushOutbox')).length===0,'交易撤回不得留下半筆outbox');
  await todos.change({operation:'complete',sourceRef:key,expectedRevision:1});
  assert((await todos.readAll())[0].status==='done','離線完成仍保存');
  assert((await records('pushOutbox'))[0].intent.enabled===false,'完成同交易排入取消');
  await push.flush({api:{...api,save:async()=>{throw Error('offline');}},epoch:'epoch-A'});
  assert((await records('pushOutbox')).length===1,'離線取消保留待同步');
  await push.flush({api,epoch:'epoch-B'});assert(calls===1,'舊epoch不能同步到新裝置');
  await push.flush({api,epoch:'epoch-A'});assert((await records('pushOutbox')).length===0,'確認後才清取消');
  // In-flight create acknowledgement must never erase a newer cancellation.
  await todos.change({operation:'reopen',sourceRef:key,expectedRevision:2});
  await push.setIntent({sourceRef:key,expectedRevision:3,intent:{enabled:true,source_version:hash,deadline:{kind:'date',value:'2026-12-01',confirmed:true,basis:'user'},remind_at:'2026-11-30T01:00:00Z'}});
  let started,release;const entered=new Promise(r=>started=r),wait=new Promise(r=>release=r);
  const flight=push.flush({api:{...api,save:async item=>{started();await wait;return {server_revision:3,client_revision:item.intent.client_revision,status:'pending'};}},epoch:'epoch-A'});
  await entered;await todos.change({operation:'remove',sourceRef:key,expectedRevision:3});release();await flight;
  assert((await records('pushOutbox'))[0].intent.enabled===false,'舊建立回覆不得清除新取消');
  out.textContent='PASS：v2→v3保留、未啟用零同步、原子abort、離線完成取消、舊epoch隔離、晚到建立回覆與取消競爭均通過。';
 }catch(e){out.textContent='FAIL：'+e.message;}finally{indexedDB.deleteDatabase(name);}
});
