/* Public campus preferences only. Never store account identity or mail text. */
(function(root){'use strict';
const KEY='nkust-office-campus-v1',CODES=['jiangong','first','nanzih','yanchao','qijin'],PATH='/public/office-mail';
function parsePreference(raw){
 if(raw===null)return null;
 const p=JSON.parse(raw);
 if(!p||Array.isArray(p)||Object.keys(p).sort().join(',')!=='campuses,skipped,version'||p.version!==1||typeof p.skipped!=='boolean'||!Array.isArray(p.campuses)||p.campuses.length>5||p.campuses.some(c=>!CODES.includes(c))||new Set(p.campuses).size!==p.campuses.length||p.skipped&&p.campuses.length)throw Error('Invalid campus preference');
 return {version:1,campuses:CODES.filter(c=>p.campuses.includes(c)),skipped:p.skipped};
}
function readPreference(storage){try{return {value:parsePreference(storage.getItem(KEY)),error:false};}catch{return {value:null,error:true};}}
function writePreference(storage,p){try{const value=parsePreference(JSON.stringify(p));storage.setItem(KEY,JSON.stringify(value));return {value,error:false};}catch{return {value:p,error:true};}}
function clearPreference(storage){try{storage.removeItem(KEY);return {value:null,error:false};}catch{return {value:null,error:true};}}
function urlFor(base,p,mode='priority'){
 const value=parsePreference(JSON.stringify(p)),u=new URL(base,'https://office.invalid');
 if(u.origin!=='https://office.invalid'||u.pathname!==PATH||!['all','priority'].includes(mode))throw Error('Invalid office path');
 const q=new URLSearchParams();for(const key of ['q','category'])if(u.searchParams.has(key))q.set(key,u.searchParams.get(key));
 q.set('mode',mode);q.set('page','1');for(const code of value.campuses)q.append('campus',code);
 return PATH+'?'+q.toString();
}
function restoreUrl(current,p){
 if(!p||p.skipped||!p.campuses.length)return null;
 const u=new URL(current,'https://office.invalid');
 if(u.searchParams.has('mode')||u.searchParams.has('campus'))return null;
 return urlFor(current,p,'priority');
}
const api={KEY,parsePreference,readPreference,writePreference,clearPreference,urlFor,restoreUrl};
if(typeof module!=='undefined')module.exports=api;
if(typeof document==='undefined')return;
document.addEventListener('DOMContentLoaded',()=>{
 const form=document.querySelector('[data-office-preference-form]');if(!form)return;
 const status=document.querySelector('[data-office-preference-status]'),retry=document.querySelector('[data-office-retry]'),temporary=document.querySelector('[data-office-temporary]');
 function storage(){try{return root.localStorage;}catch{return null;}}
 function tell(text,error=false){status.textContent=text;status.hidden=!text;retry.hidden=!error;}
 function mark(p){for(const input of form.querySelectorAll('[name="campus"]'))input.checked=p.campuses.includes(input.value);}
 function read(){const r=readPreference(storage());if(r.error){tell('無法讀取校區設定。你仍可查看全部公告，或重新選擇後僅本次套用。',true);return r;}
  const u=new URL(root.location.href);if(r.value&&!u.searchParams.has('campus'))mark(r.value);
  return r;
 }
 const initial=read();if(initial.value){const next=restoreUrl(root.location.pathname+root.location.search,initial.value);if(next){root.location.replace(next);return;}}
 retry.addEventListener('click',()=>{const r=read();if(!r.error)tell('已重新讀取此瀏覽器的校區設定。');});
 function currentBase(){const u=new URL(root.location.href);const search=document.querySelector('[data-office-search]');if(search){for(const key of ['q','category'])u.searchParams.set(key,search.querySelector('[name="'+key+'"]').value);}return u.pathname+u.search;}
 function apply(p,mode,remove=false){const next=urlFor(currentBase(),p,mode),r=remove?clearPreference(storage()):writePreference(storage(),p);
  if(r.error){tell('本次選擇可套用，但無法保存或清除此瀏覽器設定。可重試，或按「僅本次套用」。',true);temporary.href=next;temporary.hidden=false;return;}
  root.location.assign(next);
 }
 form.addEventListener('submit',event=>{event.preventDefault();const campuses=[...form.querySelectorAll('[name="campus"]:checked')].map(n=>n.value);apply({version:1,campuses,skipped:false},'priority');});
 document.querySelector('[data-office-skip]').addEventListener('click',()=>apply({version:1,campuses:[],skipped:true},'all'));
 document.querySelector('[data-office-clear]').addEventListener('click',()=>apply({version:1,campuses:[],skipped:false},'all',true));
});
})(typeof window==='undefined'?globalThis:window);
