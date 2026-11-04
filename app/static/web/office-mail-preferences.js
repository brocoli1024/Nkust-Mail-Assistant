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
function restoreSearchValues(current,received){
 for(const key of ['q','category'])current.querySelector('[name="'+key+'"]').value=received.querySelector('[name="'+key+'"]').value;
}
// Only the latest request may commit; failed requests leave the old list intact.
function createUpdater({load,commit,history,report,initialURL=null}){
 let sequence=0,controller,committedURL=initialURL;
 return async function update(url,historyMode='push'){
  const current=++sequence;controller?.abort();controller=new AbortController();
  const active=controller;report('loading');
  const timeout=setTimeout(()=>active.abort(),30000);
  try{
   const result=await load(url,active.signal);
   if(current!==sequence||active.signal.aborted)return;
   commit(result);
   if(historyMode!=='none')history(url,historyMode);
   committedURL=url;report('success');
  }catch{
   if(current===sequence){
    if(historyMode==='none'&&committedURL){history(committedURL,'replace');report('error','replace');}
    else report('error');
   }
  }finally{clearTimeout(timeout);}
 };
}
const api={createUpdater,restoreSearchValues,KEY,parsePreference,readPreference,writePreference,clearPreference,urlFor,restoreUrl};
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
 const initial=read();
 retry.addEventListener('click',()=>{const r=read();if(!r.error)tell('已重新讀取此瀏覽器的校區設定。');});
 function currentBase(){const u=new URL(root.location.href);const search=document.querySelector('[data-office-search]');if(search){for(const key of ['q','category'])u.searchParams.set(key,search.querySelector('[name="'+key+'"]').value);}return u.pathname+u.search;}
 const region=document.querySelector('[data-office-results]'),refreshRetry=document.querySelector('[data-office-refresh-retry]');
 let pending=null,successMessage='校區設定已套用，公告清單已更新。';
 function listURL(path){const u=new URL(path,root.location.origin);if(u.origin!==root.location.origin||u.pathname!==PATH)throw Error('Invalid office list');return u;}
 const update=createUpdater({
  initialURL:root.location.pathname+root.location.search,
  async load(path,signal){
   const u=listURL(path);
   const response=await root.fetch(u.href,{signal,credentials:'omit',cache:'no-store',redirect:'error',headers:{Accept:'text/html'}});
   if(!response.ok||!(response.headers.get('content-type')||'').includes('text/html'))throw Error('Office list unavailable');
   const doc=new DOMParser().parseFromString(await response.text(),'text/html');
   const next=doc.querySelector('[data-office-results]'),summary=doc.querySelector('[data-office-preferences] > summary'),search=doc.querySelector('[data-office-search]'),nav=doc.querySelector('[aria-label="公務公告排序"]');
   if(!next||!next.querySelector('[data-office-list]')||!next.querySelector('.pagination')||!summary||!search||!nav)throw Error('Invalid office list');
   return {next,summary,search,nav};
  },
  commit({next,summary,search,nav}){
   const x=root.scrollX,y=root.scrollY;
   region.replaceChildren(...next.childNodes);
   document.querySelector('[data-office-preferences] > summary').textContent=summary.textContent;
   const searchForm=document.querySelector('[data-office-search]');
   if(pending.historyMode==='none'||pending.historyMode==='replace')restoreSearchValues(searchForm,search);
   for(const input of searchForm.querySelectorAll('[name="campus"]'))input.remove();
   for(const input of search.querySelectorAll('[name="campus"]'))searchForm.append(input);
   searchForm.querySelector('[name="mode"]').value=search.querySelector('[name="mode"]').value;
   document.querySelector('[aria-label="公務公告排序"]').replaceChildren(...nav.childNodes);
   const u=new URL(pending.url,root.location.origin);mark({campuses:u.searchParams.getAll('campus')});
   document.querySelector('[data-office-campus-hint]').hidden=!(u.searchParams.get('mode')==='priority'&&!u.searchParams.has('campus'));
   root.scrollTo({left:x,top:y,behavior:'instant'});
  },
  history(path,mode){root.history[mode==='replace'?'replaceState':'pushState'](null,'',path);},
  report(state,retryMode){
   if(retryMode&&pending)pending.historyMode=retryMode;
   const x=root.scrollX,y=root.scrollY;
   const loading=state==='loading';region.setAttribute('aria-busy',String(loading));
   for(const control of form.querySelectorAll('button,fieldset'))control.disabled=loading;
   refreshRetry.hidden=state!=='error';
   if(state==='loading')tell('正在更新公告清單，完成後會套用這次校區設定。');
   else if(state==='success')tell(successMessage);
   else tell('公告清單更新失敗，仍顯示原本的結果。你的選擇已保留，請按「重試更新公告」。');
   root.scrollTo({left:x,top:y,behavior:'instant'});
  }
 });
 function refresh(url,historyMode='push',message='校區設定已套用，公告清單已更新。'){
  pending={url,historyMode};successMessage=message;return update(url,historyMode);
 }
 refreshRetry.addEventListener('click',()=>{if(pending)refresh(pending.url,pending.historyMode,successMessage);});
 temporary.addEventListener('click',event=>{event.preventDefault();refresh(temporary.getAttribute('href'),'push','本次校區排序已套用；此瀏覽器設定尚未保存。');});
 root.addEventListener('popstate',()=>{if(root.location.pathname===PATH)refresh(root.location.pathname+root.location.search,'none','已還原此網址的公告清單。');});
 if(initial.value){const next=restoreUrl(root.location.pathname+root.location.search,initial.value);if(next)refresh(next,'replace');}
 function apply(p,mode,remove=false){const next=urlFor(currentBase(),p,mode),r=remove?clearPreference(storage()):writePreference(storage(),p);
  if(r.error){tell('本次選擇可套用，但無法保存或清除此瀏覽器設定。可重試，或按「僅本次套用」。',true);temporary.href=next;temporary.hidden=false;return;}
  temporary.hidden=true;refresh(next);
 }
 form.addEventListener('submit',event=>{event.preventDefault();const campuses=[...form.querySelectorAll('[name="campus"]:checked')].map(n=>n.value);apply({version:1,campuses,skipped:false},'priority');});
 document.querySelector('[data-office-skip]').addEventListener('click',()=>apply({version:1,campuses:[],skipped:true},'all'));
 document.querySelector('[data-office-clear]').addEventListener('click',()=>apply({version:1,campuses:[],skipped:false},'all',true));
});
})(typeof window==='undefined'?globalThis:window);
