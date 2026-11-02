/* Date presentation only; no AI, inferred years, event-end guesses or writes. */
(function(root){'use strict';
const valid=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&!v.startsWith('0000')&&Number.isFinite(Date.parse(v+'T00:00:00Z'))&&new Date(v+'T00:00:00Z').toISOString().slice(0,10)===v;
function taipeiToday(now=new Date()){return new Date(now.getTime()+8*3600000).toISOString().slice(0,10);}
function dateNotices(dates,today){
 if(!valid(today))return [];
 const out=[];
 for(const d of dates){if(!['deadline','event_date'].includes(d.key)||!valid(d.value))continue;
  if(d.value<today)out.push(d.key==='deadline'?'截止日期已過，其他流程請核對來源。':'活動日期已過，是否仍可辦理請核對來源。');
  else if(d.key==='deadline'&&d.value===today)out.push('今日截止，確切時間請核對原文。');
 }return out;
}
function cardDates(card,today=taipeiToday()){
 const dates=[],article=card.source?.metadata?.article||{};
 for(const [key,label] of [['deadline','截止'],['event_date','活動']]){
  const f=card.fields?.[key];
  if(!f||!['supported','user_confirmed'].includes(f.state)||!valid(f.value)||((article.error||article.stale)&&f.origin!=='user'))continue;
  dates.push({key,label,value:f.value});
 }
 return {dates,notices:dateNotices(dates,today)};
}
const api={taipeiToday,dateNotices,cardDates};root.NkustReadingDates=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
