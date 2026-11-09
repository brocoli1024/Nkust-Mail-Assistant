/* Progressive opt-in controls; permission and server acknowledgement are distinct. */
(function(window){'use strict';
const document=window.document;
const store=window.NkustPushStore.createPushStore(),client=window.NkustPushClient.createClient();
const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
const labelTime=value=>new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',dateStyle:'short',timeStyle:'short',hourCycle:'h23'}).format(new Date(value));
const inputTime=value=>new Date(Date.parse(value)+8*3600000).toISOString().slice(0,16);
const reasons={disabled:'截止推播尚未開放；待辦仍會保存在此裝置。',home_screen_required:'iPhone／iPad 請先加入主畫面，從圖示開啟後才能設定通知（iOS 16.4 以上）。',unsupported:'此瀏覽器不支援裝置推播；仍可使用待辦與行事曆匯出。',denied:'瀏覽器已封鎖通知。若要啟用，請自行在瀏覽器的網站設定允許通知後重開此頁。',prepare_failed:'提醒功能準備失敗，請確認連線後重新開啟此頁；待辦仍保留。'};
const states={pending_sync:'提醒變更待連線同步',pending:'已排程；尚未交付推播服務',retry:'推播服務忙碌，正在等待重試',accepted:'推播服務已接受；不代表裝置已顯示或你已讀取',unknown:'發送結果不明，為避免重複通知不自動重送',cancelled:'提醒已取消',stopped:'提醒已停止，請重新核對設定',failed:'推播服務未接受，請檢查訂閱後重新設定',archived:'這次提醒已結束',needs_review:'公告已更新，請重新核對截止並儲存',conflict:'其他分頁已更新，請重新核對後儲存',device_changed:'此提醒屬於先前裝置連線，請重新確認啟用',retired_unknown:'此筆舊裝置提醒已在本機停用；伺服器取消狀態未確認，請重新設定'};
let syncing=false;
async function sync(){
 if(syncing)return;syncing=true;
 try{const device=await store.read('__device__');if(!device)return;
  if(device.pending_disable){await client.disable(device.epoch);await store.disableAcknowledged(device.epoch);}
  else{await store.flush({api:client,epoch:device.epoch});await store.reconcile({api:client});}
 }catch{}finally{syncing=false;window.dispatchEvent(new Event('nkust:push-state'));}
}
function button(parent,text,fn){const b=el('button',text);b.type='button';b.className='button secondary';b.addEventListener('click',fn);parent.append(b);return b;}
function labelled(parent,title,type){const label=el('label',title),input=el('input');input.type=type;input.required=true;label.append(input);parent.append(label);return input;}
function mount({root,record,store:localStore=store,client:localClient=client}){
 if(record.card?.source?.kind!=='public')return;
 const section=el('section');section.className='push-controls';section.setAttribute('aria-label','截止提醒');
 const status=el('p','正在準備提醒功能。');status.setAttribute('role','status');status.setAttribute('aria-live','polite');section.append(status);root.append(section);
 let binding=null,capability=null,form=null;
 async function paint(){try{
  binding=await localStore.read(record.source_ref);
  if(!section.isConnected)return;
  status.textContent=binding?states[binding.state]||'請核對提醒狀態':capability?.ready?'此待辦尚未開啟通知。':reasons[capability?.reason]||'正在準備提醒功能。';
  openButton.textContent=binding?.desired?.enabled?'重新核對提醒':'開啟截止提醒';cancelButton.disabled=!binding?.desired?.enabled;
  if(binding?.desired?.enabled&&binding.desired.remind_at)status.textContent+=' · 提醒時間：'+labelTime(binding.desired.remind_at)+'（台灣時間）';
 }catch{status.textContent='無法讀取提醒設定，請重新開啟頁面；既有待辦不會清除。';}}
 function stateChanged(){if(section.isConnected)paint();else window.removeEventListener('nkust:push-state',stateChanged);}
 window.addEventListener('nkust:push-state',stateChanged);
 async function open(){
  if(form){form.hidden=!form.hidden;return;}
  form=el('form');form.className='push-reminder-form';section.append(form);
  const note=el('p','只保存此公開公告識別、已確認日期、提醒時間及加密裝置訂閱；不會上傳整份待辦或私人修正。');form.append(note);
  const sourceStatus=el('p','正在核對公開來源版本。');sourceStatus.setAttribute('role','status');form.append(sourceStatus);
  const kindLabel=el('label','截止資訊類型'),kind=el('select');
  for(const [value,title] of [['date','只有截止日期，官方未提供時間'],['datetime','有明確截止日期與時間']]){const option=el('option',title);option.value=value;kind.append(option);}kindLabel.append(kind);form.append(kindLabel);
  const cutoff=labelled(form,'截止日期（不是活動日期）','date'),remind=labelled(form,'提醒時間（台灣時間）','datetime-local');
  const dateHelp=el('p','日期與時間必須核對原文；系統不會補猜 23:59。');form.append(dateHelp);
  const evidence=el('details');evidence.append(el('summary','查看加入待辦時的截止依據'));
  const field=record.card.fields.deadline;
  for(const e of field.evidence||[])evidence.append(el('blockquote',e.quote));
  if(!field.evidence?.length)evidence.append(el('p','此快照沒有明確截止依據，請開啟官方原文核對。'));
  const url=record.card.source.url;
  if(typeof url==='string'&&/^https:\/\/(?:[a-z0-9-]+\.)*nkust\.edu\.tw\//.test(url)){const link=el('a','開啟官方原文（另開分頁）');link.href=url;link.target='_blank';link.rel='noopener noreferrer';evidence.append(link);}form.append(evidence);
  const confirmLabel=el('label'),confirm=el('input');confirm.type='checkbox';confirm.required=true;confirmLabel.append(confirm,document.createTextNode('我已核對截止與原文，並同意開啟此筆裝置提醒。'));form.append(confirmLabel);
  const save=el('button','確認並開啟提醒');save.className='button';save.type='submit';save.disabled=true;form.append(save);
  const message=el('p');message.setAttribute('role','status');message.setAttribute('aria-live','polite');form.append(message);
  let source=null,originalValue=null;
  function deadline(){const raw=cutoff.value;return {kind:kind.value,value:kind.value==='datetime'?raw+':00+08:00':raw,confirmed:true,basis:raw===originalValue&&kind.value==='date'?'official':'user'};}
  function suggest(){
   cutoff.type=kind.value==='date'?'date':'datetime-local';
   if(!cutoff.value)return;
   try{const window=windowApi.deadlineWindow(deadline());remind.value=inputTime(window.remind_at);dateHelp.textContent=window.elapsed?'預設提醒時間已過，請另選未來且早於截止的時間。':kind.value==='date'?'只有日期：預設前一天09:00；截止日期開始後不再發送這次提醒。':'有明確時間：預設提前24小時。';}catch{remind.value='';}
  }
  const windowApi=window.NkustPushClient;
  cutoff.addEventListener('change',suggest);kind.addEventListener('change',()=>{cutoff.value='';suggest();});
  form.addEventListener('submit',event=>{
   event.preventDefault();if(save.disabled||!source||!form.reportValidity())return;
   let confirmed,when;
   try{confirmed=deadline();const limit=windowApi.deadlineWindow(confirmed);when=new Date(remind.value+':00+08:00').toISOString();if(Date.parse(when)<=Date.now()||Date.parse(when)>=Date.parse(limit.expires_at))throw Error();}
   catch{message.textContent='請選擇未來且早於截止的提醒時間。';return;}
   save.disabled=true;message.textContent='請依瀏覽器提示授權，正在完成提醒設定。';
   // Direct click-stack call; all source/config/SW preparation already finished.
   const subscription=localClient.subscribeFromClick();
   subscription.then(async device=>{
    await localStore.setDevice(device);
    const saved=await localStore.setIntent({sourceRef:record.source_ref,expectedRevision:record.revision,intent:{enabled:true,source_version:source.version,deadline:confirmed,remind_at:when}});
    await localStore.flush({api:localClient,epoch:device.epoch});
    const acknowledged=await localStore.read(record.source_ref);
    const pending=acknowledged?.desired?.operation_id!==saved.desired.operation_id||!['pending','accepted','retry'].includes(acknowledged?.state);
    message.textContent=pending?'已存此裝置，提醒變更待連線同步；尚未確認伺服器排程。':'提醒已排程；推播可能因網路、系統設定或裝置離線延遲。';
    await paint();window.dispatchEvent(new Event('nkust:push-state'));
   }).catch(error=>{message.textContent=error.code==='PUSH_SUBSCRIPTION_IN_USE'||error.code==='PUSH_DEVICE_UNAUTHORIZED'?'裝置連線已失效。請到「此裝置提醒設定」重設訂閱，再重新確認此筆提醒。':'此筆提醒尚未完成啟用；請檢查通知權限與連線後重試，待辦仍保留。';})
    .finally(()=>{save.disabled=false;});
  });
  try{
   source=await localClient.source(record.source_ref);
   const meta=await localStore.read('__device__');
   if(meta?.pending_disable){sourceStatus.textContent='全部提醒仍在等待關閉同步，請先恢復連線完成關閉。';return;}
   const matched=record.card.source.metadata?.push_source_version===source.version;
   if(matched&&field.value&&['supported','user_confirmed'].includes(field.state)){cutoff.value=field.value;originalValue=field.state==='supported'?field.value:null;suggest();}
   sourceStatus.textContent=matched?'已找到此公開公告，請確認下列日期。':'來源版本與加入時不同，或舊待辦未留存版本；請重讀官方原文，自行填入已核對的截止。';save.disabled=false;
  }catch{sourceStatus.textContent='無法確認此公開來源；請確認連線或從公告詳情重新加入。既有待辦保留。';}
 }
 const openButton=button(section,'開啟截止提醒',open);openButton.disabled=true;
 if(binding?.desired?.enabled)openButton.textContent='重新核對提醒';
 const cancelButton=button(section,'取消此筆提醒',async()=>{
  try{binding=await localStore.read(record.source_ref);if(!binding)return;
   await localStore.setIntent({sourceRef:record.source_ref,expectedRevision:record.revision,intent:{enabled:false,source_version:binding.desired.source_version}});
   await paint();sync();
  }catch{status.textContent='取消尚未完成，請重新讀取設定後再試；不會宣稱伺服器已取消。';}
 });
 localClient.prepare().then(cap=>{capability=cap;openButton.disabled=!cap.ready||record.effective_status==='done';paint();});
}
async function deviceControls(root){
 const status=root.querySelector('[data-push-device-status]'),test=root.querySelector('[data-push-test]'),disable=root.querySelector('[data-push-disable]'),reset=root.querySelector('[data-push-reset]'),retry=root.querySelector('[data-push-retry]');
 const cap=await client.prepare();let meta=null;
 async function refresh(){
  meta=await store.read('__device__').catch(()=>null);
  status.textContent=meta?.pending_disable?'提醒關閉待連線同步。':cap.ready?(meta?'此裝置已連線，各筆提醒狀態請看待辦下方。':'提醒預設關閉，請在各待辦自行開啟。'):reasons[cap.reason];
  test.disabled=!cap.ready||!meta||!!meta.pending_disable;disable.disabled=!meta||!!meta.pending_disable;reset.disabled=!cap.ready;
 }
 await refresh();window.addEventListener('nkust:push-state',refresh);
 test.addEventListener('click',async()=>{test.disabled=true;try{await client.test(window.crypto.randomUUID(),meta.epoch);status.textContent='測試通知已排入發送；請查看裝置通知，不代表裝置已收到。';}catch{status.textContent='測試通知尚未成功排入，請檢查連線與此裝置訂閱。';}finally{test.disabled=false;}});
 retry?.addEventListener('click',async()=>{retry.disabled=true;try{await sync();await refresh();}finally{retry.disabled=false;}});
 disable.addEventListener('click',async()=>{
  disable.disabled=true;
  try{await store.requestDisable(meta.epoch);await client.disable(meta.epoch);await store.disableAcknowledged(meta.epoch);status.textContent='此裝置全部提醒已關閉。';}
  catch{status.textContent='提醒關閉待連線同步；尚未確認伺服器停止。請保持此頁並恢復連線。';}
  finally{window.dispatchEvent(new Event('nkust:push-state'));}
 });
 reset.addEventListener('click',async()=>{reset.disabled=true;try{const previous=await store.read('__device__');await client.reset(previous?.epoch);if(previous)await store.retireDevice(previous.epoch);status.textContent='已重設此瀏覽器連線，待辦保留。先前伺服器取消狀態未確認，請在需要的待辦重新核對啟用。';}catch{status.textContent='重設尚未完成，請確認連線後重試。';}finally{reset.disabled=false;}});
 if(meta)sync();
}
window.NkustPushUI={mount};
window.addEventListener('online',sync);window.addEventListener('nkust:todo-changed',sync);
document.addEventListener('DOMContentLoaded',()=>{for(const root of document.querySelectorAll('[data-push-device]'))deviceControls(root).catch(()=>{});});
})(window);
