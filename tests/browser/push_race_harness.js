document.getElementById('run').addEventListener('click',async()=>{
 const out=document.getElementById('result'),name='nkust-push-race-'+crypto.randomUUID(),factory={open:(_,v)=>indexedDB.open(name,v)},push=NkustPushStore.createPushStore({indexedDB:factory}),todos=NkustTodos.createTodoStore({indexedDB:factory});
 const assert=(v,m)=>{if(!v)throw Error(m);},hash='a'.repeat(64);
 const card=ref=>({source:{kind:'public',source_ref:ref,title:'合成競爭驗收'},baseline_hash:hash,fields:{deadline:{value:null,state:'pending'}}});
 try{
  for(const ref of ['one','two'])await todos.change({operation:'add',card:card(ref),sourceRef:ref,expectedRevision:0});
  await push.setDevice({epoch:'A'});
  const add=ref=>push.setIntent({sourceRef:ref,expectedRevision:1,intent:{enabled:true,source_version:hash,deadline:{kind:'date',value:'2026-12-20',confirmed:true,basis:'user'}}});
  await add('one');let entered,release;const began=new Promise(r=>entered=r),wait=new Promise(r=>release=r);let calls=0;
  const api={list:async()=>({device:{epoch:'A'},items:[]}),save:async item=>{calls++;if(calls===1){entered();await wait;}return {server_revision:1,client_revision:item.intent.client_revision,status:'pending'};}};
  const first=push.flush({api,epoch:'A'});await began;await add('two');const second=push.flush({api,epoch:'A'});release();await Promise.all([first,second]);
  assert(calls===2&&(await push.read('two')).state==='pending','第二筆在busy期間加入後必須真正送出，不能只宣稱已排程');
  await push.setDevice({epoch:'B'});await push.disableAcknowledged('A');assert((await push.read('__device__')).epoch==='B','舊裝置取消回覆不得清掉新裝置');
  await push.setDevice({epoch:'A'});await push.requestDisable();await push.retireDevice('A');assert((await push.read('__device__'))===null,'遺失取消回覆後可明確重設本機');
  assert((await todos.readAll()).length===2,'重設不得刪除待辦');
  out.textContent='PASS：busy期間第二筆確實同步、舊epoch回覆隔離、遺失取消回覆後重設及待辦保留。';
 }catch(e){out.textContent='FAIL：'+e.message;}finally{indexedDB.deleteDatabase(name);}
});
