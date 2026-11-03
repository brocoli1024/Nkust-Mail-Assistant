/* Public list navigation only; per-tab storage never contains Gmail or corrections. */
(function(root){'use strict';
const LIST='/public/office-mail',KEY='nkust-office-reading-v1',TTL=30*60*1000;
function validPath(path){
 if(typeof path!=='string'||path.length>3000||!path.startsWith(LIST)||/[\\\r\n]/.test(path))return false;
 try{const u=new URL(path,'https://public.invalid');return u.origin==='https://public.invalid'&&u.pathname===LIST&&!u.hash&&[...u.searchParams.keys()].every(k=>['q','category','campus','mode','page'].includes(k));}catch{return false;}
}
function canonicalPath(path){
 if(!validPath(path))return null;
 const q=new URL(path,'https://public.invalid').searchParams;
 return JSON.stringify([q.get('q')||'',q.get('category')||'',q.getAll('campus').sort().join(','),q.get('mode')||'all',q.get('page')||'1']);
}
function readingRecord(path,id,y,at){
 if(!validPath(path)||!/^\d+$/.test(id)||!Number.isFinite(y)||y<0||y>10000000||!Number.isFinite(at))return null;
 return {path,id,y:Math.round(y),at};
}
function restoreOffset(record,path,hash,now){
 if(!record||!readingRecord(record.path,record.id,record.y,record.at)||canonicalPath(record.path)!==canonicalPath(path)||hash!=='#office-'+record.id||!Number.isFinite(now)||now<record.at||now-record.at>TTL)return null;
 return record.y;
}
if(typeof module!=='undefined')module.exports={readingRecord,restoreOffset};
if(typeof document==='undefined')return;
document.addEventListener('DOMContentLoaded',()=>{
 const list=document.querySelector('[data-office-list]');if(!list)return;
 list.addEventListener('click',event=>{
  const link=event.target.closest('a[data-office-reading-id]');if(!link)return;
  const record=readingRecord(location.pathname+location.search,link.dataset.officeReadingId,root.scrollY,Date.now());
  try{if(record)sessionStorage.setItem(KEY,JSON.stringify(record));}catch{/* The row anchor remains a usable fallback. */}
 });
 root.addEventListener('pageshow',()=>{
  let y;try{y=restoreOffset(JSON.parse(sessionStorage.getItem(KEY)),location.pathname+location.search,location.hash,Date.now());}catch{return;}
  if(y===null)return;
  let cancelled=false;
  const cancel=()=>{cancelled=true;};
  for(const name of ['pointerdown','keydown','wheel','touchstart'])root.addEventListener(name,cancel,{once:true,passive:true});
  const restore=()=>root.requestAnimationFrame(()=>{if(!cancelled)root.scrollTo({top:y,behavior:'instant'});});
  restore();document.fonts?.ready.then(restore);
 });
});
})(typeof window==='undefined'?globalThis:window);
