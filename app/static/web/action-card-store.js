/* Atomic device storage for public announcements only. */
(function(root){
'use strict';
const HASH=/^[a-f0-9]{64}$/;
function helpers(){return root.NkustActionCards||(typeof require==='function'?require('./action-card.js'):null);}
function validateRecord(r,key){
  if(r==null)return null;
  if(r.schema_version!==1||r.source_ref!==key||!Number.isSafeInteger(r.revision)||r.revision<1||!r.baselines||!Array.isArray(r.revisions)||r.revisions.length!==r.revision)throw Error('STORAGE_CORRUPT');
  for(const [hash,card] of Object.entries(r.baselines))if(!HASH.test(hash)||card?.source?.kind!=='public'||card.source.source_ref!==key||card.baseline_hash!==hash)throw Error('STORAGE_CORRUPT');
  for(const [i,v] of r.revisions.entries()){
    if(v.revision!==i+1||!r.baselines[v.baseline_hash]||!['save','reset'].includes(v.operation))throw Error('STORAGE_CORRUPT');
    try{helpers().validateCorrectionPatch(v.patch);}catch{throw Error('STORAGE_CORRUPT');}
  }
  return r;
}
function createActionCardStore(options={}){
  const factory=options.indexedDB??root.indexedDB;
  function open(){return new Promise((resolve,reject)=>{
    if(!factory){reject(Error('STORAGE_UNAVAILABLE'));return;}
    let req,done=false;
    try{req=factory.open('nkust-campus-assistant',1);}catch{reject(Error('STORAGE_UNAVAILABLE'));return;}
    req.onupgradeneeded=()=>{if(!req.result.objectStoreNames.contains('publicActionCards'))req.result.createObjectStore('publicActionCards',{keyPath:'source_ref'});};
    req.onerror=()=>{done=true;reject(Error('STORAGE_UNAVAILABLE'));};
    req.onblocked=()=>{done=true;reject(Error('STORAGE_UNAVAILABLE'));};
    req.onsuccess=()=>{if(done){req.result.close();return;}resolve(req.result);};
  });}
  async function transaction(key,mode,modify){
    const db=await open();
    try{return await new Promise((resolve,reject)=>{
      let tx,result,failure;
      try{
        tx=db.transaction('publicActionCards',mode);
        tx.oncomplete=()=>failure?reject(failure):resolve(result);
        tx.onabort=tx.onerror=()=>reject(failure||Error(tx.error?.name==='QuotaExceededError'?'STORAGE_QUOTA':'STORAGE_UNAVAILABLE'));
        const records=tx.objectStore('publicActionCards'),req=records.get(key);
        req.onerror=()=>{failure=Error('STORAGE_UNAVAILABLE');};
        req.onsuccess=()=>{
          try{const old=validateRecord(req.result,key);result=modify?modify(old,records):old;}
          catch(e){failure=e.name==='QuotaExceededError'?Error('STORAGE_QUOTA'):e;tx.abort();}
        };
      }catch(e){failure=Error(e.name==='QuotaExceededError'?'STORAGE_QUOTA':'STORAGE_UNAVAILABLE');try{tx?.abort();}catch{}reject(failure);}
    });}finally{db.close();}
  }
  return {
    read(key){return transaction(key,'readonly');},
    async commit({card,patch,operation,expectedRevision,now=new Date().toISOString()}){
      if(card?.source?.kind!=='public')throw TypeError('PRIVATE_SOURCE_NOT_ALLOWED');
      if(!HASH.test(card.baseline_hash)||typeof card.source.source_ref!=='string'||!Number.isSafeInteger(expectedRevision)||expectedRevision<0||!['save','reset'].includes(operation))throw Error('INVALID_PATCH');
      const normalized=helpers().validateCorrectionPatch(operation==='save'?patch:{fields:{}});
      return transaction(card.source.source_ref,'readwrite',(old,records)=>{
        if((old?.revision||0)!==expectedRevision)throw Error('REVISION_CONFLICT');
        const r=old||{schema_version:1,source_ref:card.source.source_ref,revision:0,baselines:{},revisions:[]};
        if(!Object.hasOwn(r.baselines,card.baseline_hash))r.baselines[card.baseline_hash]=structuredClone(card);
        r.revision++;
        r.revisions.push({revision:r.revision,baseline_hash:card.baseline_hash,operation,patch:normalized,created_at:now});
        records.put(r);return r;
      });
    },
    erase(key,expectedRevision){return transaction(key,'readwrite',(old,records)=>{if((old?.revision||0)!==expectedRevision)throw Error('REVISION_CONFLICT');records.delete(key);});}
  };
}
const api={createActionCardStore};root.NkustActionCardStore=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
