/* Read-only public device badges. Never upload todos or inspect account data. */
(function(root){'use strict';
function todoLabel(records,ref,project,now=new Date()){
 const r=records.find(r=>r.source_ref===ref&&r.card?.source?.kind==='public');
 if(!r||r.status==='removed')return '';
 const state=project(r,now).effective_status;
 return {active:'待辦：進行中',done:'待辦：已完成',snoozed:'待辦：稍後處理'}[state]||'';
}
if(typeof module!=='undefined')module.exports={todoLabel};
if(typeof document==='undefined')return;
document.addEventListener('DOMContentLoaded',()=>{
 const list=document.querySelector('[data-public-list]');if(!list)return;
 const badges=[...list.querySelectorAll('[data-list-todo-ref]')],status=document.querySelector('[data-list-storage-status]'),retry=document.querySelector('[data-list-storage-retry]');
 let records=[],ready=false,loading=false;
 function paint(){
  for(const badge of badges){badge.textContent=ready?todoLabel(records,badge.dataset.listTodoRef,root.NkustTodos.projectTodo):'';badge.hidden=!badge.textContent;}
  const dates=root.NkustReadingDates;if(!dates)return;
  for(const item of list.querySelectorAll('.announcement')){
   const box=item.querySelector('[data-list-date-notices]');
   try{const notices=dates.dateNotices(JSON.parse(item.querySelector('[data-reading-dates]').dataset.readingDates),dates.taipeiToday());box.replaceChildren();for(const text of notices){const s=document.createElement('span');s.textContent=text;box.append(s);}}catch{/* Retain server-rendered dates on unsupported markup. */}
  }
 }
 async function load(){
  if(loading)return;loading=true;
  try{records=await root.NkustTodos.createTodoStore().readAll();ready=true;paint();status.hidden=true;retry.hidden=true;}
  catch{ready=false;records=[];for(const badge of badges){badge.hidden=true;badge.textContent='';}status.textContent='無法讀取此裝置的待辦狀態，並非沒有待辦；公告仍可閱讀。';status.hidden=false;retry.hidden=false;}
  finally{loading=false;}
 }
 retry?.addEventListener('click',load);
 root.addEventListener('pageshow',load);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
 root.setInterval(()=>{try{paint();}catch{/* Invalid stored records must never become public content. */}},60000);
 load();
});
})(typeof window==='undefined'?globalThis:window);
