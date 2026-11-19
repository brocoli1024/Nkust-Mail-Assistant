/* Private-page clock only; never writes storage or calls a data API. */
(function(){
'use strict';
function needsTodoRefresh(values,now){return values.some(value=>/(?:Z|[+-]\d{2}:\d{2})$/.test(value)&&Number.isFinite(Date.parse(value))&&Date.parse(value)<=now);}
if(typeof module!=='undefined')module.exports={needsTodoRefresh};
if(typeof document==='undefined')return;
document.addEventListener('DOMContentLoaded',()=>{
 const due=Array.from(document.querySelectorAll('[data-snoozed-until]')).map(n=>n.dataset.snoozedUntil).filter(Boolean);
 setInterval(()=>{if(needsTodoRefresh(due,Date.now()))location.reload();},60000);
});
})();
