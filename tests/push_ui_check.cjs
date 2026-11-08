const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
let device=null,offline=true,ready;
class Element{constructor(){this.handlers={};this.disabled=true;this.textContent='';}addEventListener(name,fn){this.handlers[name]=fn;}}
const nodes=Object.fromEntries(['status','test','disable','reset','retry'].map(k=>[k,new Element()]));
const panel={querySelector:selector=>nodes[selector.includes('device-status')?'status':selector.match(/data-push-([a-z]+)/)[1]]};
const events=new EventTarget();
const store={read:async()=>device,requestDisable:async()=>{device.pending_disable=true;},disableAcknowledged:async()=>{device=null;},flush:async()=>({pending:0}),reconcile:async()=>({})};
const client={prepare:async()=>({ready:true}),disable:async()=>{if(offline)throw Error('offline');},unsubscribeBrowser:async()=>{},test:async()=>{}};
const window={document:{querySelectorAll:()=>[panel],addEventListener:(_,fn)=>ready=fn},NkustPushStore:{createPushStore:()=>store},NkustPushClient:{createClient:()=>client},addEventListener:events.addEventListener.bind(events),dispatchEvent:events.dispatchEvent.bind(events),Event,crypto:require('node:crypto').webcrypto};
vm.runInNewContext(fs.readFileSync('app/static/web/push-ui.js','utf8'),{window,Event,Intl,Date});
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 ready();await tick();assert.equal(nodes.test.disabled,true);
 device={epoch:'epoch-A'};events.dispatchEvent(new Event('nkust:push-state'));await tick();assert.equal(nodes.test.disabled,false,'first successful enable must immediately unlock test without reload');
 await nodes.disable.handlers.click();await tick();assert.equal(device.pending_disable,true);assert.match(nodes.status.textContent,/待連線同步/);
 offline=false;events.dispatchEvent(new Event('online'));await tick();await tick();assert.equal(device,null);assert.doesNotMatch(nodes.status.textContent,/待連線同步/);
 console.log('push UI immediate enable and offline all-disable recovery passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
