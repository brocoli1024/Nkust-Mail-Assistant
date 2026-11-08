/* Browser permission is requested only inside an explicit click stack. */
(function(root){'use strict';
function deadlineWindow(deadline,now=Date.now()){
 const expiry=Date.parse(deadline.kind==='date'?deadline.value+'T00:00:00+08:00':deadline.value);
 const suggested=deadline.kind==='date'?expiry-15*3600000:expiry-24*3600000;
 if(!Number.isFinite(expiry))throw Error('PUSH_DATE_CONFIRMATION_REQUIRED');
 return {expires_at:new Date(expiry).toISOString(),remind_at:new Date(suggested).toISOString(),elapsed:suggested<=now};
}
function createClient(env=root){
 let capability={status:'loading',ready:false},registration=null,prepared=null;
 async function api(path,method='GET',payload){
  const options={method,credentials:'same-origin',cache:'no-store'};
  if(payload!==undefined){options.headers={'Content-Type':'application/json'};options.body=JSON.stringify(payload);}
  if(env.AbortSignal?.timeout)options.signal=env.AbortSignal.timeout(20000);
  const response=await env.fetch('/api/push'+path,options);
  const data=await response.json();
  if(!response.ok){const error=Error('PUSH_API_FAILED');error.code=data.error||data.detail||'PUSH_API_FAILED';throw error;}
  return data;
 }
 function prepare(){
  if(prepared)return prepared;
  prepared=(async()=>{
   try{
    const config=await api('/config');if(!config.enabled)return capability={ready:false,status:'disabled',reason:'disabled'};
    const nav=env.navigator||{},ios=/iPhone|iPad|iPod/.test(nav.userAgent||'')||/Macintosh/.test(nav.userAgent||'')&&nav.maxTouchPoints>1;
    if(ios&&!(nav.standalone||env.matchMedia?.('(display-mode: standalone)').matches))return capability={ready:false,status:'unsupported',reason:'home_screen_required'};
    if(!env.isSecureContext||!env.Notification||!env.PushManager||!nav.serviceWorker)return capability={ready:false,status:'unsupported',reason:'unsupported'};
    if(env.Notification.permission==='denied')return capability={ready:false,status:'denied',reason:'denied'};
    await nav.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'});
    let timer;try{registration=await Promise.race([nav.serviceWorker.ready,new Promise((_,reject)=>timer=env.setTimeout(()=>reject(Error('SW_NOT_READY')),8000))]);}finally{env.clearTimeout(timer);}
    const raw=env.atob(config.publicKey.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-config.publicKey.length%4)%4));
    const key=Uint8Array.from(raw,c=>c.charCodeAt(0));
    return capability={ready:true,status:'ready',key};
   }catch{return capability={ready:false,status:'error',reason:'prepare_failed'};}
  })();return prepared;
 }
 function subscribeFromClick(){
  if(!capability.ready||!registration)return Promise.reject(Error('PUSH_NOT_READY'));
  // No await, fetch, database or permission lookup may precede this call.
  let subscriptionPromise;
  try{subscriptionPromise=registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:capability.key});}
  catch(error){capability={...capability,status:'incomplete'};return Promise.reject(error);}
  return subscriptionPromise.then(subscription=>api('/device','POST',{subscription:subscription.toJSON()}))
   .then(device=>{capability={...capability,status:'active'};return device;})
   .catch(error=>{capability={...capability,status:'incomplete'};throw error;});
 }
 async function unsubscribeBrowser(){const reg=registration||await env.navigator?.serviceWorker?.getRegistration?.('/');const sub=await reg?.pushManager.getSubscription();if(sub)await sub.unsubscribe();}
 async function reset(){await unsubscribeBrowser();await api('/device/reset','POST',{});capability={...capability,status:'ready'};}
 return {prepare,subscribeFromClick,state:()=>capability,api,
  list:()=>api('/reminders'),save:item=>api('/reminders/'+item.intent.todo_id,'PUT',{intent:item.intent,expected_revision:item.expected_revision}),
  source:sourceRef=>api('/source','POST',{source_ref:sourceRef}),test:operationId=>api('/test','POST',{operation_id:operationId}),
  disable:()=>api('/device','DELETE',{}),unsubscribeBrowser,reset};
}
root.NkustPushClient={createClient,deadlineWindow};if(typeof module!=='undefined')module.exports=root.NkustPushClient;
})(typeof window!=='undefined'?window:globalThis);
