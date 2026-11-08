const assert=require('node:assert/strict');
const {createClient,deadlineWindow}=require('../app/static/web/push-client.js');
function environment(fail=false){const calls=[];const registration={pushManager:{subscribe(options){calls.push('subscribe');return Promise.resolve({toJSON:()=>({endpoint:'https://fcm.googleapis.com/synthetic',keys:{}})});}}};
const env={isSecureContext:true,PushManager:function(){},Notification:{permission:'default'},navigator:{userAgent:'iPhone',standalone:true,serviceWorker:{register:async()=>registration,ready:Promise.resolve(registration)}},matchMedia:()=>({matches:true}),atob:s=>Buffer.from(s,'base64').toString('binary'),setTimeout,clearTimeout,
fetch:async(url,options)=>{calls.push(url);if(url.endsWith('/config'))return {ok:true,json:async()=>({enabled:true,publicKey:'YQ'})};if(fail)throw Error('network');return {ok:true,json:async()=>({id:'device',epoch:'epoch-A'})};}};return {env,calls};}
(async()=>{
 const {env,calls}=environment();const client=createClient(env);await client.prepare();calls.length=0;
 const promise=client.subscribeFromClick();assert.equal(calls[0],'subscribe','subscription must happen in the click stack before fetch');await promise;assert.equal(calls[1],'/api/push/device');
 const failed=environment(true),bad=createClient(failed.env);await bad.prepare();await assert.rejects(bad.subscribeFromClick());assert.notEqual(bad.state().status,'active','browser grant alone is incomplete');
 const tab=environment();tab.env.navigator.standalone=false;tab.env.matchMedia=()=>({matches:false});const unsupported=createClient(tab.env);assert.equal((await unsupported.prepare()).reason,'home_screen_required');
 const d=deadlineWindow({kind:'date',value:'2026-11-10'},Date.parse('2026-11-08T00:00:00Z'));assert.equal(d.remind_at,'2026-11-09T01:00:00.000Z');assert.equal(d.expires_at,'2026-11-09T16:00:00.000Z');
 console.log('push client gesture, failure and date contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
