/* Minimal opt-in intent/outbox only. Original cards never leave this database. */
(function(root){'use strict';
const STORES=['publicActionCards','publicTodos','pushBindings','pushOutbox'];
function createPushStore(options={}){
 const factory=options.indexedDB??root.indexedDB;
 function open(){return new Promise((resolve,reject)=>{
  if(!factory){reject(Error('STORAGE_UNAVAILABLE'));return;}let request,failed=false;
  try{request=factory.open('nkust-campus-assistant',3);}catch{reject(Error('STORAGE_UNAVAILABLE'));return;}
  request.onupgradeneeded=()=>{for(const name of STORES)if(!request.result.objectStoreNames.contains(name))request.result.createObjectStore(name,{keyPath:'source_ref'});};
  request.onblocked=request.onerror=()=>{failed=true;reject(Error('STORAGE_UNAVAILABLE'));};
  request.onsuccess=()=>{if(failed){request.result.close();return;}request.result.onversionchange=()=>request.result.close();resolve(request.result);};
 });}
 async function tx(mode,work){const db=await open();try{return await new Promise((resolve,reject)=>{
  let failure,value;const transaction=db.transaction(STORES,mode);
  transaction.oncomplete=()=>resolve(value);transaction.onabort=transaction.onerror=()=>reject(failure||Error('STORAGE_UNAVAILABLE'));
  const fail=e=>{failure=e;try{transaction.abort();}catch{}};
  try{work(transaction,result=>value=result,fail);}catch(e){fail(e);}
 });}finally{db.close();}}
 function get(transaction,store,key,callback,fail){const r=transaction.objectStore(store).get(key);r.onsuccess=()=>{try{callback(r.result);}catch(e){fail(e);}};r.onerror=()=>fail(Error('STORAGE_UNAVAILABLE'));}
 function read(sourceRef){return tx('readonly',(t,set,fail)=>get(t,'pushBindings',sourceRef,r=>set(r||null),fail));}
 async function setDevice(device){return tx('readwrite',(t,set)=>{t.objectStore('pushBindings').put({source_ref:'__device__',...device});set(device);});}
 async function setIntent({sourceRef,intent,expectedRevision}){
  return tx('readwrite',(t,set,fail)=>get(t,'publicTodos',sourceRef,todo=>{
   if(!todo||todo.card?.source?.kind!=='public'||todo.revision!==expectedRevision)throw Error('REVISION_CONFLICT');
   if(intent.enabled&&['done','removed'].includes(todo.status))throw Error('TODO_INACTIVE');
   for(const key of Object.keys(intent))if(!['enabled','source_version','deadline','remind_at'].includes(key))throw Error('INVALID_REMINDER');
   get(t,'pushBindings','__device__',device=>{
    if(!device?.epoch)throw Error('DEVICE_NOT_READY');
    get(t,'pushBindings',sourceRef,old=>{
     const same=old?.epoch===device.epoch;
     const revision=Math.max(same?old?.client_revision||0:0,todo.revision)+1;
     const desired={todo_id:same?old.todo_id:root.crypto.randomUUID(),source_ref:sourceRef,source_version:String(intent.source_version||''),
      client_revision:revision,operation_id:root.crypto.randomUUID(),enabled:intent.enabled===true,
      deadline:intent.enabled?structuredClone(intent.deadline):null,remind_at:intent.enabled?intent.remind_at||null:null};
     const binding={source_ref:sourceRef,todo_id:desired.todo_id,epoch:device.epoch,client_revision:revision,
      server_revision:same?old.server_revision??null:null,desired,state:'pending_sync'};
     t.objectStore('pushBindings').put(binding);
     t.objectStore('pushOutbox').put({source_ref:sourceRef,epoch:device.epoch,intent:desired,expected_revision:binding.server_revision});set(binding);
    },fail);
   },fail);
  },fail));
 }
 async function outbox(){return tx('readonly',(t,set)=>{const r=t.objectStore('pushOutbox').getAll();r.onsuccess=()=>set(r.result);});}
 async function acknowledge(item,result){return tx('readwrite',(t,set,fail)=>get(t,'pushBindings',item.source_ref,binding=>{
  if(!binding||binding.epoch!==item.epoch)return;
  get(t,'pushOutbox',item.source_ref,current=>{
   binding.server_revision=Math.max(binding.server_revision||0,result.server_revision);
   if(current?.intent.operation_id===item.intent.operation_id){t.objectStore('pushOutbox').delete(item.source_ref);binding.state=result.status;}
   t.objectStore('pushBindings').put(binding);set(binding);
  },fail);
 },fail));}
 async function mark(item,state){return tx('readwrite',(t,set,fail)=>get(t,'pushBindings',item.source_ref,binding=>{
  if(binding?.desired?.operation_id===item.intent.operation_id){binding.state=state;t.objectStore('pushBindings').put(binding);}
 },fail));}
 let flushing=false;
 async function flush({api,epoch}){
  if(flushing)return {busy:true};flushing=true;let synced=0,pending=0;
  try{
   const items=await outbox();if(!items.length)return {synced,pending};
   let remote;try{remote=await api.list();}catch{return {synced,pending:items.length,unauthorized:true};}
   if(remote.device.epoch!==epoch)return {synced,pending:items.length,deviceChanged:true};
   for(const item of items){
    if(item.epoch!==epoch){pending++;await mark(item,'device_changed');continue;}
    try{const result=await api.save(item);await acknowledge(item,result);synced++;}
    catch(e){pending++;await mark(item,e.code==='PUSH_SOURCE_CHANGED'?'needs_review':e.code==='PUSH_REVISION_CONFLICT'?'conflict':'pending_sync');}
   }
   return {synced,pending};
  }finally{flushing=false;}
 }
 async function reconcile({api}){
  const local=await read('__device__');if(!local?.epoch)return null;
  const remote=await api.list();if(remote.device.epoch!==local.epoch)throw Error('DEVICE_CHANGED');
  await tx('readwrite',(t,set,fail)=>{
   for(const item of remote.items)get(t,'pushBindings',item.source_ref,binding=>{
    if(binding?.epoch===local.epoch&&binding.client_revision===item.client_revision&&binding.state!=='pending_sync'){
     binding.state=item.status;binding.server_revision=item.server_revision;t.objectStore('pushBindings').put(binding);
    }
   },fail);
  });return remote;
 }
 async function disableAcknowledged(epoch){return tx('readwrite',(t,set,fail)=>{
  const r=t.objectStore('pushBindings').getAll();r.onsuccess=()=>{try{
   for(const b of r.result)if(b.source_ref!=='__device__'&&b.epoch===epoch){b.state='cancelled';b.desired.enabled=false;t.objectStore('pushBindings').put(b);t.objectStore('pushOutbox').delete(b.source_ref);}
   t.objectStore('pushBindings').delete('__device__');
  }catch(e){fail(e);}};
 });}
 return {read,setDevice,setIntent,flush,reconcile,disableAcknowledged};
}
root.NkustPushStore={createPushStore};if(typeof module!=='undefined')module.exports=root.NkustPushStore;
})(typeof window!=='undefined'?window:globalThis);
