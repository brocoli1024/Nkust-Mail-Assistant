/* Optional home-screen guidance. Acceptance is not proof of standalone mode. */
(function(global){'use strict';
function detectInstallContext(env){
 const nav=env.navigator||{},ua=nav.userAgent||'';
 const ios=/iPhone|iPad|iPod/.test(ua)||/Macintosh/.test(ua)&&nav.maxTouchPoints>1;
 return {ios,safari:/Safari/.test(ua)&&!/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua),standalone:!!(nav.standalone||env.matchMedia?.('(display-mode: standalone)').matches)};
}
function mount({root,window:env,storage}){
 const find=name=>root.querySelector('[data-install-'+name+']');
 const open=find('open'),dialog=find('dialog');if(!open||!dialog)return;
 const close=find('close'),native=find('native'),status=find('status'),ios=find('ios'),other=find('other'),safari=find('safari');
 const context=detectInstallContext(env);let prompt=null;
 ios.hidden=!context.ios;other.hidden=context.ios;safari.hidden=!context.ios||context.safari;native.hidden=true;
 if(context.standalone){open.textContent='已在App模式';open.disabled=true;status.textContent='目前已從主畫面 App 開啟。';}
 open.addEventListener('click',()=>{if(!context.standalone)dialog.showModal();});
 close.addEventListener('click',()=>{dialog.close();try{storage?.setItem('nkust-install-dismissed-v1','1');}catch{}});
 env.addEventListener('beforeinstallprompt',event=>{event.preventDefault();if(context.standalone||context.ios)return;prompt=event;native.hidden=false;});
 native.addEventListener('click',async()=>{
  if(!prompt)return;const current=prompt;prompt=null;native.disabled=true;
  try{await current.prompt();const choice=await current.userChoice;
   status.textContent=choice.outcome==='accepted'?'已接受安裝提示，請從新增的圖示開啟；是否為App模式以實際開啟方式判斷。':'已略過安裝，你仍可繼續瀏覽。';
  }catch{status.textContent='無法開啟安裝提示，請依瀏覽器選單步驟操作。';}
  finally{native.hidden=true;}
 });
 env.addEventListener('appinstalled',()=>{status.textContent='瀏覽器回報已完成安裝，請從主畫面圖示開啟。';native.hidden=true;});
}
const api={mount,detectInstallContext};global.NkustInstallGuide=api;
if(typeof module!=='undefined')module.exports=api;
if(global.document)global.document.addEventListener('DOMContentLoaded',()=>{
 let storage;try{storage=global.localStorage;}catch{}
 mount({root:global.document,window:global,storage});
});
})(typeof window!=='undefined'?window:globalThis);
