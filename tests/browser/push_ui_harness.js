document.addEventListener('DOMContentLoaded',async()=>{
 const out=document.getElementById('result'),name='nkust-push-ui-qa-'+crypto.randomUUID(),factory={open:(_,version)=>indexedDB.open(name,version)};
 const todos=NkustTodos.createTodoStore({indexedDB:factory}),store=NkustPushStore.createPushStore({indexedDB:factory}),ref=JSON.stringify(['nkust-office-mail','https://officemail.nkust.edu.tw/Mail/MailView/69929']),hash='a'.repeat(64);
 const day=new Date(Date.now()+8*86400000).toISOString().slice(0,10);
 const card={source:{kind:'public',source_ref:ref,title:'合成公務公告',url:'https://officemail.nkust.edu.tw/Mail/MailView/69929',metadata:{push_source_version:hash}},baseline_hash:hash,fields:{deadline:{value:day,state:'supported',evidence:[{quote:'合成測試截止：'+day}]}}};
 let subscribed=0,calls=[];
 const client={prepare:async()=>({ready:true}),source:async()=>({version:hash}),subscribeFromClick(){subscribed++;return Promise.resolve({epoch:'ui-epoch-A'});},list:async()=>({device:{epoch:'ui-epoch-A'},items:[]}),save:async item=>{calls.push(item);return {server_revision:1,client_revision:item.intent.client_revision,status:item.intent.enabled?'pending':'cancelled'};}};
 try{await todos.change({operation:'add',card,sourceRef:ref,expectedRevision:0});const record=(await todos.readAll())[0];record.effective_status='active';
 window.addEventListener('nkust:push-state',async()=>{
  if(!calls.length)return;
  const binding=await store.read(ref),payload=JSON.stringify(calls);
  if(subscribed===1&&binding.state==='pending'&&!payload.includes('baseline_hash')&&!payload.includes('合成公務公告'))out.textContent='PASS：明確確認才啟用、日期型提醒、伺服器確認及最少資料同步。';
  else out.textContent='FAIL：啟用或資料邊界不符。';
 });
 NkustPushUI.mount({root:document.getElementById('fixture'),record,store,client});out.textContent='請點開啟截止提醒，核對合成日期並勾選確認。';
 }catch(e){out.textContent='FAIL：'+e.message;}
 window.addEventListener('pagehide',()=>indexedDB.deleteDatabase(name),{once:true});
});
