/* Device-only public todos. No network calls and no private sources. */
(function(root){'use strict';
const HASH=/^[a-f0-9]{64}$/;
function dateNow(now){const d=new Date(now??Date.now());if(!Number.isFinite(d.getTime()))throw Error('INVALID_TIME');return d;}
function taipeiDate(now){return new Date(dateNow(now).getTime()+8*3600000).toISOString().slice(0,10);}
function nextSnooze(now){const d=new Date(dateNow(now).getTime()+8*3600000);return new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()+1,1)).toISOString();}
function validate(r,allowDemo=false){
 if(!r||r.schema_version!==1||typeof r.source_ref!=='string'||!(r.card?.source?.kind==='public'||allowDemo&&r.card?.source?.kind==='demo')||r.card.source.source_ref!==r.source_ref||!HASH.test(r.card.baseline_hash)||!r.card.fields?.deadline||!Number.isSafeInteger(r.revision)||r.revision<1||!['active','done','snoozed','removed'].includes(r.status)||!Number.isFinite(Date.parse(r.created_at))||!Number.isFinite(Date.parse(r.updated_at))||((r.status==='snoozed')!==!!r.snoozed_until)||(r.snoozed_until&&!Number.isFinite(Date.parse(r.snoozed_until))))throw Error('STORAGE_CORRUPT');
 const d=r.card.fields.deadline;if(d.value&&['supported','user_confirmed'].includes(d.state)){const parsed=new Date(d.value+'T00:00:00Z');if(!/^\d{4}-\d{2}-\d{2}$/.test(d.value)||!Number.isFinite(parsed.getTime())||parsed.toISOString().slice(0,10)!==d.value)throw Error('STORAGE_CORRUPT');}
 return r;
}
function projectTodo(r,now){
 validate(r,true);const today=taipeiDate(now),d=r.card.fields.deadline,deadline=d.value&&['supported','user_confirmed'].includes(d.state)?d.value:null;
 const end=new Date(dateNow(now).getTime()+8*3600000+6*86400000).toISOString().slice(0,10);
 return {...r,effective_status:r.status==='snoozed'&&Date.parse(r.snoozed_until)<=dateNow(now).getTime()?'active':r.status,
 deadline,deadline_group:!deadline?'none':deadline<today?'overdue':deadline===today?'today':deadline<=end?'soon':'later',snooze_after_deadline:!!deadline&&deadline<taipeiDate(nextSnooze(now))};
}
function createTodoStore(options={}){
 const factory=options.indexedDB??root.indexedDB;
 function open(){return new Promise((resolve,reject)=>{
  if(!factory){reject(Error('STORAGE_UNAVAILABLE'));return;}let request,failed=false;
  try{request=factory.open('nkust-campus-assistant',2);}catch{reject(Error('STORAGE_UNAVAILABLE'));return;}
  request.onupgradeneeded=()=>{for(const name of ['publicActionCards','publicTodos'])if(!request.result.objectStoreNames.contains(name))request.result.createObjectStore(name,{keyPath:'source_ref'});};
  request.onblocked=request.onerror=()=>{failed=true;reject(Error('STORAGE_UNAVAILABLE'));};
  request.onsuccess=()=>{if(failed){request.result.close();return;}resolve(request.result);};
 });}
 async function transaction(sourceRef,modify){const db=await open();try{return await new Promise((resolve,reject)=>{
 let tx,result,failure;
 try{tx=db.transaction('publicTodos',modify?'readwrite':'readonly');tx.oncomplete=()=>failure?reject(failure):resolve(result);tx.onabort=tx.onerror=()=>reject(failure||Error(tx.error?.name==='QuotaExceededError'?'STORAGE_QUOTA':'STORAGE_UNAVAILABLE'));
 const store=tx.objectStore('publicTodos'),request=modify?store.get(sourceRef):store.getAll();
 request.onerror=()=>{failure=Error('STORAGE_UNAVAILABLE');};request.onsuccess=()=>{try{if(modify){const old=request.result?validate(request.result):null;result=modify(old);validate(result);store.put(result);}else result=request.result.map(r=>validate(r));}catch(e){failure=e.name==='QuotaExceededError'?Error('STORAGE_QUOTA'):e;tx.abort();}};
 }catch(e){failure=Error(e.name==='QuotaExceededError'?'STORAGE_QUOTA':'STORAGE_UNAVAILABLE');try{tx?.abort();}catch{}reject(failure);}
 });}finally{db.close();}}
 return {readAll(){return transaction();},async change({operation,card,sourceRef,expectedRevision,now=new Date().toISOString(),snoozeUntil}){
 if(operation==='add'&&card?.source?.kind!=='public')throw TypeError('PRIVATE_SOURCE_NOT_ALLOWED');
 if(!['add','complete','reopen','snooze','remove'].includes(operation)||typeof sourceRef!=='string'||!Number.isSafeInteger(expectedRevision)||expectedRevision<0)throw Error('INVALID_TODO');
 if(operation==='snooze'&&snoozeUntil!==undefined&&dateNow(snoozeUntil).toISOString()!==nextSnooze(now))throw Error('STALE_SNOOZE');
 const timestamp=dateNow(now).toISOString();
 return transaction(sourceRef,old=>{if((old?.revision||0)!==expectedRevision)throw Error('REVISION_CONFLICT');
  if(operation==='add'){if(old&&old.status!=='removed')throw Error('REVISION_CONFLICT');return {schema_version:1,source_ref:sourceRef,card:structuredClone(card),status:'active',snoozed_until:null,revision:expectedRevision+1,created_at:timestamp,updated_at:timestamp};}
  if(!old||old.status==='removed')throw Error('REVISION_CONFLICT');
  return {...old,status:{complete:'done',reopen:'active',snooze:'snoozed',remove:'removed'}[operation],snoozed_until:operation==='snooze'?nextSnooze(now):null,revision:expectedRevision+1,updated_at:timestamp};
 });}};
}
const api={createTodoStore,nextSnooze,projectTodo};root.NkustTodos=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
