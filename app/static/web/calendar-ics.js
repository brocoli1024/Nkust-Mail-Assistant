/* RFC5545 files built in memory. No storage, network, calendar API or AI. */
(function(root){'use strict';
const encoder=new TextEncoder();
const clip=(text,max)=>Array.from(typeof text==='string'?text:'').slice(0,max).join('');
function projectCard(card,{snapshot=false}={}){
 return {schema_version:1,source:{kind:card.source.kind,source_ref:card.source.source_ref,title:clip(card.source.title,500),url:card.source.url||null},baseline_hash:card.baseline_hash,
 summary:clip(card.fields.summary?.value,160),action:clip(card.fields.action?.value,1200),
 dates:Object.fromEntries(['event_date','deadline'].map(key=>[key,{value:card.fields[key]?.value??null,state:card.fields[key]?.state??'pending',evidence:(card.fields[key]?.evidence||[]).slice(0,5).map(e=>clip(typeof e==='string'?e:e.quote,2000))}])),time_status:card.time_status||'unknown',context:snapshot?'snapshot':'current'};
}
function isoDate(value){
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||value.startsWith('0000'))throw Error('INVALID_DATE');
 const d=new Date(value+'T00:00:00Z');if(!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==value)throw Error('INVALID_DATE');return d;
}
function escapeText(value){return String(value??'').replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,').replace(/[\x00-\x1f\x7f]/g,'');}
function foldLine(line){let out='',bytes=0;for(const char of line){const size=encoder.encode(char).length;if(bytes+size>75){out+='\r\n ';bytes=1;}out+=char;bytes+=size;}return out;}
function safeURL(value){
 if(typeof value!=='string'||value.length>4096||/[\s\x00-\x1f\x7f\\]/.test(value))return null;
 try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}
}
function taipeiToUTC(date,time){
 isoDate(date);if(typeof time!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(time))throw Error('INVALID_TIME');
 const wall=Date.parse(date+'T'+time+':00Z'),wanted=date+'T'+time+':00';
 let formatter;try{formatter=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});}catch{throw Error('TIMEZONE_UNAVAILABLE');}
 const local=instant=>{const p=Object.fromEntries(formatter.formatToParts(new Date(instant)).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));return p.year.padStart(4,'0')+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute+':'+p.second;};
 let candidate=wall-8*3600000;
 for(let i=0;i<4&&local(candidate)!==wanted;i++)candidate+=wall-Date.parse(local(candidate)+'Z');
 if(local(candidate)!==wanted)throw Error('TIME_NOT_UNIQUE');
 for(const delta of [-7200000,-3600000,3600000,7200000])if(local(candidate+delta)===wanted)throw Error('TIME_NOT_UNIQUE');
 const result=new Date(candidate);if(result.getUTCFullYear()<1||result.getUTCFullYear()>9999)throw Error('DATE_RANGE');return result;
}
function validateSelection(payload,selection){
 if(payload?.schema_version!==1||!['public','private','demo'].includes(payload.source?.kind)||typeof payload.source.source_ref!=='string'||!payload.source.source_ref||payload.source.source_ref.length>8192||typeof payload.source.title!=='string'||!['current','snapshot'].includes(payload.context))throw Error('INVALID_PAYLOAD');
 if(selection?.confirmed!==true)throw Error('CONFIRM_REQUIRED');
 if(!['event_date','deadline'].includes(selection.kind)||!['all_day','timed'].includes(selection.mode))throw Error('INVALID_SELECTION');
 const field=payload.dates?.[selection.kind];if(!field||!['supported','user_confirmed'].includes(field.state)||!field.value)throw Error('DATE_PENDING');
 const date=isoDate(field.value);let start,end;
 if(selection.mode==='all_day'){
  if(selection.startTime||selection.endDateTime)throw Error('INVALID_SELECTION');
  end=new Date(date.getTime()+86400000);if(end.getUTCFullYear()>9999)throw Error('DATE_RANGE');
  start=date;
 }else{
  start=taipeiToUTC(field.value,selection.startTime);
  if(selection.endDateTime){if(typeof selection.endDateTime!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(selection.endDateTime))throw Error('INVALID_END');const [d,t]=selection.endDateTime.split('T');end=taipeiToUTC(d,t);if(end<=start)throw Error('INVALID_END');}
 }
 return {kind:selection.kind,mode:selection.mode,date:field.value,start,end};
}
const stamp=date=>date.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
async function buildCalendar(payload,selection,options={}){
 const chosen=validateSelection(payload,selection),crypto=Object.hasOwn(options,'crypto')?options.crypto:root.crypto;
 if(!crypto?.subtle?.digest)throw Error('CRYPTO_UNAVAILABLE');
 const now=options.now??new Date();if(!(now instanceof Date)||!Number.isFinite(now.getTime())||now.getUTCFullYear()<1||now.getUTCFullYear()>9999)throw Error('INVALID_TIME');
 const bytes=await crypto.subtle.digest('SHA-256',encoder.encode(JSON.stringify([payload.source.kind,payload.source.source_ref,chosen.kind])));
 const uid=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('')+'@nkust-mail-assistant.invalid';
 const label=chosen.kind==='deadline'?'截止事項':'活動',demo=payload.source.kind==='demo',url=safeURL(payload.source.url);
 const sourceLabel={public:'公開公告',private:'私人Gmail公告（原文需回本站核對）',demo:'合成示範，非真實公告'}[payload.source.kind];
 const evidence=(payload.dates[chosen.kind].evidence||[]).slice(0,5).map(e=>clip(e,2000)).join('\n');
 const description=[sourceLabel,'來源標題：'+clip(payload.source.title,500),url?'來源：'+url:'來源未提供可匯出的網址，請回本站查看原文。',
  '資訊版本：'+(payload.context==='snapshot'?'待辦加入時快照':'目前畫面版本')+'；來源變更不會更新已下載檔案。',
  '摘要：'+clip(payload.summary,160),'行動：'+clip(payload.action,1200),'所選日期依據節錄：'+(evidence||'無引文；請核對來源與個人修正。'),
  '日期與時間已由使用者確認，時區Asia/Taipei。',chosen.mode==='all_day'?'全天事件，不包含時間。':'未提供結束時間時不推定持續長度。',
  '適用對象不代表符合資格。下載檔案不代表已加入行事曆。',payload.source.kind==='private'?'含私人資訊；CLASS:PRIVATE僅提示，檔案仍是可分享的純文字。':''].filter(Boolean).join('\n');
 const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Nkust-Mail-Assistant//Campus Calendar Export//ZH-TW','CALSCALE:GREGORIAN','BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+stamp(now)];
 if(chosen.mode==='all_day')lines.push('DTSTART;VALUE=DATE:'+chosen.date.replace(/-/g,''),'DTEND;VALUE=DATE:'+chosen.end.toISOString().slice(0,10).replace(/-/g,''));
 else{lines.push('DTSTART:'+stamp(chosen.start));if(chosen.end)lines.push('DTEND:'+stamp(chosen.end));}
 lines.push('SUMMARY:'+escapeText((demo?'【合成示範】':'')+label+'｜'+clip(payload.source.title,500)),'DESCRIPTION:'+escapeText(description));
 if(url)lines.push('URL:'+url);if(payload.source.kind==='private')lines.push('CLASS:PRIVATE');
 lines.push('END:VEVENT','END:VCALENDAR');
 return {text:lines.map(foldLine).join('\r\n')+'\r\n',filename:'nkust-'+payload.source.kind+'-'+(chosen.kind==='deadline'?'deadline':'event')+'-'+chosen.date+'.ics'};
}
const api={projectCard,buildCalendar,validateSelection,foldLine,escapeText,taipeiToUTC,safeURL};root.NkustCalendar=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
