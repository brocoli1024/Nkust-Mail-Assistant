/* Confirmation UI; calendar content stays in this page until an explicit download. */
(function(root){'use strict';
const controls=new WeakMap();
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const errors={DATE_PENDING:'日期待確認，請先核對原文並在公告詳情修正；待辦快照不會自動更新。',CONFIRM_REQUIRED:'請先核對日期、時間與來源，再勾選確認。',INVALID_DATE:'日期格式或實際日期不正確，請回公告詳情核對。',INVALID_TIME:'請填入有效開始時間（HH:MM）。',INVALID_END:'結束日期時間必須有效且晚於開始時間。',TIME_NOT_UNIQUE:'此台灣時間不存在或不唯一，無法安全匯出；請重新核對。',DATE_RANGE:'日期超出可安全匯出的範圍。',CRYPTO_UNAVAILABLE:'此瀏覽器無法安全產生檔案識別，請使用支援的HTTPS或本機瀏覽器。',TIMEZONE_UNAVAILABLE:'此瀏覽器無法確認Asia/Taipei時區，尚未下載。',STALE_SELECTION:'畫面或選項已變更，請重新確認後下載。',INVALID_SELECTION:'請選擇活動或截止，以及全天或定時方式。',DOWNLOAD_UNAVAILABLE:'此瀏覽器不支援檔案下載；尚未確認成功。'};
function initialize(node,initial,{wait=false,dirty=false}={}){
 if(controls.has(node))return controls.get(node);
 const api=root.NkustCalendar,ui=node.querySelector('[data-calendar-ui]')||node.appendChild(el('div'));ui.hidden=false;
 const status=el('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.dataset.calendarStatus='';
 if(!api){status.textContent='此瀏覽器無法產生行事曆檔案，請更新瀏覽器；原公告仍可閱讀。';ui.append(status);return null;}
 let payload=structuredClone(initial),waiting=wait,changed=dirty,busy=false,version=0;
 const details=el('details'),summary=el('summary','下載行事曆檔案（.ics）');details.append(summary);
 const fields=el('fieldset'),legend=el('legend','選擇並確認日期與時間');fields.append(legend);
 const label=(text,input)=>{const l=el('label',text);l.append(input);fields.append(l);return input;};
 const select=(name,items)=>{const n=el('select');n.dataset[name]='';for(const [v,t] of items){const option=el('option',t);option.value=v;n.append(option);}return n;};
 const kind=label('匯出事項',select('calendarKind',[['','請選擇'],['event_date','活動日期'],['deadline','截止事項']]));
 const dateInfo=el('p');dateInfo.dataset.calendarDate='';fields.append(dateInfo);
 const evidence=el('details'),evidenceTitle=el('summary','查看日期依據節錄'),quotes=el('div');evidence.append(evidenceTitle,quotes);fields.append(evidence);
 const source=el('p');fields.append(source);
 const mode=label('紀錄方式',select('calendarMode',[['','請選擇'],['all_day','全天事件（不包含時間）'],['timed','我已核對時間，填入台灣時間']]));
 const timeWarning=el('p');fields.append(timeWarning);
 const timeGroup=el('div'),startLabel=el('label','開始時間（Asia/Taipei）'),start=el('input');start.type='time';start.step='60';start.dataset.calendarStart='';startLabel.append(start);
 const endLabel=el('label','結束日期時間（選填，Asia/Taipei）'),end=el('input');end.type='datetime-local';end.step='60';end.dataset.calendarEnd='';endLabel.append(end);
 timeGroup.append(startLabel,endLabel,el('p','未填結束時間時不推定一小時或任何持續長度。'));fields.append(timeGroup);
 const preview=el('p');preview.dataset.calendarPreview='';fields.append(preview);
 const confirmLabel=el('label'),confirm=el('input');confirm.type='checkbox';confirm.dataset.calendarConfirm='';confirmLabel.append(confirm,document.createTextNode('我已核對原文、日期及上述方式；全天不含時間，定時以台灣時間匯出。'));fields.append(confirmLabel);
 const download=el('button','下載 .ics 檔案');download.type='button';download.className='button secondary';download.dataset.calendarDownload='';fields.append(download);
 details.append(fields,status);ui.append(details);
 function selection(){return {kind:kind.value,mode:mode.value,confirmed:confirm.checked,startTime:mode.value==='timed'?start.value:null,endDateTime:mode.value==='timed'?(end.value||null):null};}
 function render(){
  fields.disabled=busy||waiting||changed;
  const field=payload.dates?.[kind.value],supported=field&&['supported','user_confirmed'].includes(field.state)&&field.value;
  dateInfo.textContent=kind.value?((kind.value==='event_date'?'活動日期':'截止事項')+'：'+(supported?field.value:'待確認')+(field?.state==='user_confirmed'?' · 我的修正，非系統驗證':'')):'請分別選擇活動日期或截止事項。';
  quotes.replaceChildren();for(const text of field?.evidence||[])quotes.append(el('blockquote',text));if(!field?.evidence?.length)quotes.append(el('p','沒有可顯示的日期引文，請核對原文與個人修正。'));
  const url=api.safeURL(payload.source.url);source.replaceChildren(el('span','來源：'+payload.source.title+' '));if(url){const a=el('a','核對原文（另開分頁）');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.className='text-link dark';source.append(a);}else source.append(el('span','未提供安全的來源網址，請回本站查看原文。'));
  timeWarning.textContent=payload.time_status==='unparsed'?'原文可能含尚未解析的時間，請核對後明確選擇紀錄方式；不會自動把時間當成全天。':'日期已提供，仍請核對原文是否有開始與結束時間。';
  timeGroup.hidden=mode.value!=='timed';
  preview.textContent=supported&&mode.value?(mode.value==='all_day'?'預覽：'+field.value+' 全天，不包含時間。':'預覽：'+field.value+' '+(start.value||'開始待填')+' → '+(end.value||'不推定結束時間')+'（Asia/Taipei）')+(payload.context==='snapshot'?' · 待辦加入時快照':' · 目前畫面版本'):'';
  download.disabled=busy||waiting||changed||!supported||!mode.value||!confirm.checked;
  if(waiting)status.textContent='正在等待已保存的行動卡載入；修正讀取失敗時不會改用空白基準匯出。';
  else if(changed)status.textContent='修正尚未保存，請先儲存或重新載入頁面，再核對匯出。';
  else if(kind.value&&!supported)status.textContent=errors.DATE_PENDING;
 }
 const resetConfirmation=()=>{version++;confirm.checked=false;status.textContent='選項已變更，請重新核對並確認。';render();};
 kind.addEventListener('change',()=>{mode.value=payload.time_status==='unparsed'?'':'all_day';resetConfirmation();});
 for(const input of [mode,start,end]){input.addEventListener('input',resetConfirmation);input.addEventListener('change',resetConfirmation);}
 confirm.addEventListener('change',()=>{version++;status.textContent=confirm.checked?'已確認畫面選項；按下載才會產生檔案。':'請核對後勾選確認。';render();});
 download.addEventListener('click',async()=>{
  if(waiting||changed||busy)return;const ticket=version,p=structuredClone(payload),s=selection();busy=true;render();status.textContent='正在產生行事曆檔案，請稍候。';
  let objectURL;
  try{
   if(typeof Blob!=='function'||typeof URL.createObjectURL!=='function')throw Error('DOWNLOAD_UNAVAILABLE');
   const file=await api.buildCalendar(p,s);
   if(ticket!==version||waiting||changed)throw Error('STALE_SELECTION');
   objectURL=URL.createObjectURL(new Blob([file.text],{type:'text/calendar;charset=utf-8'}));
   const a=el('a');a.href=objectURL;a.download=file.filename;a.hidden=true;document.body.append(a);try{a.click();}finally{a.remove();}
   const revoke=objectURL;setTimeout(()=>URL.revokeObjectURL(revoke),60000);objectURL=null;
   status.textContent='已產生檔案並啟動下載，請確認瀏覽器下載清單；尚未驗證加入行事曆。';
  }catch(e){if(objectURL)URL.revokeObjectURL(objectURL);status.textContent=errors[e.message]||'無法確認下載成功，請檢查選項與瀏覽器下載權限後重試。';}
  finally{busy=false;render();}
 });
 const controller={update(next){version++;payload=structuredClone(next);waiting=false;changed=false;kind.value='';mode.value='';start.value='';end.value='';confirm.checked=false;status.textContent='行動卡已載入，請選擇事項並重新核對。';render();},dirty(){version++;changed=true;confirm.checked=false;render();}};
 controls.set(node,controller);render();
 const parent=node.closest('.action-card');if(parent&&!parent.hasAttribute('data-card-payload'))parent.querySelector('form.card-editor')?.addEventListener('input',()=>controller.dirty());
 return controller;
}
function mount(parent,payload,options={}){
 const node=el('section');node.className='calendar-export';node.dataset.calendarPayload=JSON.stringify(payload);node.append(el('h3','行事曆匯出'),el('p','選擇活動或截止並確認後，產生檔案並啟動下載；不代表已加入行事曆。'));
 node.append(el('p',payload.context==='snapshot'?'此處匯出待辦加入時快照，來源可能已更新，不會自動套用最新修正。':'匯出目前畫面版本，來源後續變更不會更新檔案。'));
 if(payload.source.kind==='private')node.append(el('p','含私人資訊的純文字檔案，請勿隨意轉傳。'));if(payload.source.kind==='demo')node.append(el('p','合成示範，非真實公告。'));
 const ui=el('div');ui.dataset.calendarUi='';node.append(ui);parent.append(node);initialize(node,payload,options);return node;
}
root.NkustCalendarUI={mount,setCard(parent,card){const node=parent.querySelector('[data-calendar-payload]');if(node)controls.get(node)?.update(root.NkustCalendar.projectCard(card));},setDirty(parent){const node=parent.querySelector('[data-calendar-payload]');if(node)controls.get(node)?.dirty();}};
document.addEventListener('DOMContentLoaded',()=>{for(const node of document.querySelectorAll('[data-calendar-payload]')){try{initialize(node,JSON.parse(node.dataset.calendarPayload),{wait:node.hasAttribute('data-calendar-wait'),dirty:node.hasAttribute('data-calendar-dirty')});}catch{node.append(el('p','匯出資訊無法讀取，請重新載入頁面；尚未下載。'));}}});
})(window);
