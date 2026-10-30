/* Shared device/demo presentation. DOM text only; no uploads or private reads. */
(function(root){'use strict';
const api=root.NkustTodos,controllers=new WeakMap();
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const labelTime=iso=>new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',dateStyle:'short',timeStyle:'short',hourCycle:'h23'}).format(new Date(iso));
function safeLink(url){try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function makeMemory(){let record=null;return {async readAll(){return record?[structuredClone(record)]:[];},async change(o){
 if(o.operation==='snooze'&&o.snoozeUntil!==api.nextSnooze())throw Error('STALE_SNOOZE');
 if((record?.revision||0)!==o.expectedRevision)throw Error('REVISION_CONFLICT');const stamp=new Date().toISOString();
 if(o.operation==='add'){if(record&&record.status!=='removed')throw Error('REVISION_CONFLICT');record={schema_version:1,source_ref:o.sourceRef,card:structuredClone(o.card),status:'active',snoozed_until:null,revision:o.expectedRevision+1,created_at:stamp,updated_at:stamp};}
 else{if(!record||record.status==='removed')throw Error('REVISION_CONFLICT');record={...record,status:{complete:'done',reopen:'active',snooze:'snoozed',remove:'removed'}[o.operation],revision:record.revision+1,snoozed_until:o.operation==='snooze'?api.nextSnooze():null,updated_at:stamp};}return structuredClone(record);
 }};}
function init(){
 for(const area of document.querySelectorAll('[data-device-todo], [data-todo-list]')){
  const detail=area.hasAttribute('data-device-todo'),scope=area.dataset.scope||'public',cardNode=detail?area.closest('[data-card-payload]'):null;
  if(!['public','demo'].includes(scope))continue;
  const status=area.querySelector('[data-todo-status]'),body=area.querySelector(detail?'[data-todo-actions]':'[data-todo-items]');
  const store=scope==='demo'?makeMemory():api.createTodoStore();let records=[],card=null,dirty=false,ready=false,busy=false,clockKey='';
  const say=text=>{status.textContent=text;};
  const button=(target,text,fn)=>{const b=el('button',text);b.type='button';b.className='button secondary';b.disabled=busy; b.addEventListener('click',fn);target.append(b);};
  async function change(operation,old,snoozeUntil){
   if(!ready||busy)return;if(operation==='add'&&(!card||dirty)){say('請先讀取行動卡，並儲存或恢復尚未保存的修正，再加入待辦。');return;}
   if(operation==='remove'&&!root.confirm('移除此待辦？公告與修正仍保留，可從公告詳情重新加入。'))return;
   busy=true;render();say('正在保存待辦，請稍候。');
   try{await store.change({operation,card:operation==='add'?card:undefined,sourceRef:old?.source_ref||card.source.source_ref,expectedRevision:old?.revision||0,snoozeUntil});records=await store.readAll();say(scope==='demo'?'示範待辦已更新；重新載入即重設。':'待辦已保存至此裝置。');}
   catch(e){ready=false;say(e.message==='STALE_SNOOZE'?'日期已跨日，本次未稍後；請重新讀取待辦並確認新的時間與截止提醒。':e.message==='REVISION_CONFLICT'?'其他頁面已更新，本次未覆寫；請按重新讀取待辦後核對。':'保存結果無法確認，請重新讀取待辦；既有資料未清除。');}
   finally{busy=false;render();}
  }
  function actions(target,r){
   if(r.effective_status!=='done')button(target,'標記完成',()=>change('complete',r));
   if(r.effective_status!=='active')button(target,'重新開啟',()=>change('reopen',r));
   const shownSnooze=api.nextSnooze();
   target.append(el('p','稍後至 '+labelTime(shownSnooze)+'（明天09:00，台灣時間）重新出現；不發送通知。'));
   if(r.snooze_after_deadline)target.append(el('p','此稍後時間晚於截止日期，請先處理。'));
   button(target,'稍後處理',()=>change('snooze',r,shownSnooze));button(target,'移除待辦',()=>change('remove',r));
  }
  function row(r){const article=el('article');article.className='detail-card todo-row';article.append(el('h3',r.card.source.title||'公告待辦'));
   article.append(el('p',r.card.fields.action?.value||r.card.fields.summary?.value||'行動待確認，請核對原文。'));
   article.append(el('p','截止：'+(r.deadline||'待確認')+({overdue:' · 已逾期',today:' · 今日截止',soon:' · 即將截止'}[r.deadline_group]||'')));
   if(r.effective_status==='snoozed')article.append(el('p','稍後至 '+labelTime(r.snoozed_until)+'（台灣時間）'));
   article.append(el('p','加入時的資訊快照，來源後續可能更新；不代表你符合資格。'));
   const url=safeLink(r.card.source.url);if(url){const link=el('a','核對公告來源（另開分頁）');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.className='text-link dark';article.append(link);}
   const history=el('details'),summary=el('summary','加入時的原文與依據'),pre=el('pre',JSON.stringify(r.card,null,2));history.append(summary,pre);article.append(history);
   if(root.NkustCalendarUI?.mount&&root.NkustCalendar?.projectCard){
    try{root.NkustCalendarUI.mount(article,root.NkustCalendar.projectCard(r.card,{snapshot:true}));}
    catch{article.append(el('p','行事曆匯出暫時無法使用；待辦仍可操作。'));}
   }else article.append(el('p','行事曆匯出暫時無法使用；待辦仍可操作。'));
   const controls=el('div');controls.className='actions todo-actions';actions(controls,r);article.append(controls);return article;
  }
  function render(){clockKey=api.renderClockKey(records,new Date());body.replaceChildren();if(!ready){body.append(el('p','尚未完整讀取待辦，請重試。'));return;}
   const projected=records.map(r=>api.projectTodo(r,new Date()));
   if(detail){const old=projected.find(r=>r.source_ref===card?.source.source_ref);
    if(!card){body.append(el('p','請先完成行動卡載入；修正讀取失敗時不會使用空白值加入。'));return;}
    if(!old||old.status==='removed'){button(body,'加入我的待辦',()=>change('add',old));}
    else{body.append(el('p','已加入 · '+({active:'進行中',done:'已完成',snoozed:'稍後處理'}[old.effective_status])));if(old.card.baseline_hash!==card.baseline_hash)body.append(el('p','目前來源或解析版本與加入時不同，請核對；待辦保留加入時資訊。'));actions(body,old);}
   }else{
    const filter=area.querySelector('[data-todo-filter]')?.value||'active';
    const selected=projected.filter(r=>r.effective_status===filter).sort((a,b)=>(a.deadline||'9999').localeCompare(b.deadline||'9999'));
    if(!selected.length)body.append(el('p','此狀態尚無待辦。到公開公告詳情按「加入我的待辦」開始。'));
    for(const r of selected)body.append(row(r));
   }
  }
  async function load(){if(busy)return;ready=false;say('正在讀取待辦。');try{records=await store.readAll();ready=true;say(scope==='demo'?'示範待辦只留在此頁。':'已讀取此裝置待辦；不會隨 Google 帳號切換。');}catch{say('待辦讀取失敗，並非沒有待辦。請檢查儲存權限、關閉舊分頁後重試；不會清除既有資料。');}render();}
  if(detail)controllers.set(cardNode,{setCard(value){card=structuredClone(value);dirty=false;render();},setDirty(){dirty=true;}});
  const retry=el('button','重新讀取待辦');retry.type='button';retry.className='button secondary';retry.addEventListener('click',load);area.append(retry);
  area.querySelector('[data-todo-filter]')?.addEventListener('change',render);setInterval(()=>{if(ready&&!busy&&clockKey!==api.renderClockKey(records,new Date()))render();},60000);load();
 }
}
root.NkustTodoUI={setCard(node,card){controllers.get(node)?.setCard(card);},setDirty(node){controllers.get(node)?.setDirty();}};
document.addEventListener('DOMContentLoaded',init);
})(window);
