/* Private-page clock only; never writes storage or calls a data API. */
document.addEventListener('DOMContentLoaded',()=>{
  const due=Array.from(document.querySelectorAll('[data-snoozed-until]')).map(n=>Date.parse(n.dataset.snoozedUntil)).filter(Number.isFinite);
  const opened=Date.now();setInterval(()=>{if(due.some(t=>t>opened&&t<=Date.now()))location.reload();},60000);
});
