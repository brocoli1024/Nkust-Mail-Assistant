document.getElementById('run').addEventListener('click',async()=>{
 const out=document.getElementById('result'),name='nkust-rollback-qa-'+crypto.randomUUID(),factory={open:(_,v)=>indexedDB.open(name,v)},hash='a'.repeat(64),key='rollback-synthetic';
 const card={source:{kind:'public',source_ref:key,title:'合成回復驗收'},baseline_hash:hash,fields:{deadline:{value:null,state:'pending'}}};
 const assert=(v,m)=>{if(!v)throw Error(m);};
 const script=src=>new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.head.append(s);});
 try{
  const todos=NkustTodos.createTodoStore({indexedDB:factory}),push=NkustPushStore.createPushStore({indexedDB:factory});
  await todos.change({operation:'add',card,sourceRef:key,expectedRevision:0});
  await push.setDevice({epoch:'rollback-A'});await push.setIntent({sourceRef:key,expectedRevision:1,intent:{enabled:true,source_version:hash,deadline:{kind:'date',value:'2026-12-20',confirmed:true,basis:'user'}}});
  await new Promise((resolve,reject)=>{const r=indexedDB.open(name,3);r.onerror=reject;r.onsuccess=()=>{const db=r.result,tx=db.transaction('publicActionCards','readwrite');tx.objectStore('publicActionCards').put({schema_version:1,source_ref:key,revision:1,baselines:{[hash]:card},revisions:[{revision:1,baseline_hash:hash,operation:'reset',patch:{fields:{}}}]});tx.oncomplete=()=>{db.close();resolve();};};});
  await script('/__qa/rollback-assets/todo-store.js');await script('/__qa/rollback-assets/action-card-store.js');
  const rollback=NkustTodos.createTodoStore({indexedDB:factory});assert((await rollback.readAll())[0].revision===1,'回復仍可讀v3待辦');
  assert((await NkustActionCardStore.createActionCardStore({indexedDB:factory}).read(key)).revision===1,'回復保留修正歷史');
  await rollback.change({operation:'complete',sourceRef:key,expectedRevision:1});
  assert((await push.read(key)).desired.enabled===false,'回復仍原子排入取消');
  out.textContent='PASS：相容回復程式可讀v3待辦與修正歷史，保留資料且仍原子排入取消。';
 }catch(e){out.textContent='FAIL：'+e.message;}finally{indexedDB.deleteDatabase(name);}
});
