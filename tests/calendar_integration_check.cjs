'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.handlers={};this.hidden=false;this.value='';this.dataset={};this.children=[];}
 addEventListener(name,fn){this.handlers[name]=fn;}
 fire(name){return this.handlers[name]?.();}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
async function actionCardBoundary(initialFailure=false){
 const keys=['summary','action','audience','materials','deadline','event_date'];
 const base={source:{kind:'public',source_ref:'synthetic',segments:[]},baseline_hash:'a'.repeat(64),fields:Object.fromEntries(keys.map(k=>[k,{value:k==='event_date'?'2026-11-20':null,state:k==='event_date'?'supported':'pending',evidence:[],warnings:[]}])),requires_action:null,deadline_kind:'unknown'};
 base.source.segments=[{kind:'excerpt',text:'合成依據'}];base.fields.summary.evidence=[{segment:0,quote:'合成依據'}];
 const root=new Element(),editor=new Element(),nodes=new Map();editor.hidden=true;
 root.dataset.cardPayload=JSON.stringify({scope:'public',base_card:base,taipei_today:'2026-10-30'});
 const inputs=keys.flatMap(k=>['mode','value','quote','confirmed'].map(part=>{const n=new Element();n.name=k+'.'+part;n.value=part==='mode'?'inherit':'';return n;}));
 for(const name of ['action_decision','deadline_kind']){const n=new Element();n.name=name;n.value='unknown';inputs.push(n);}
 editor.querySelectorAll=()=>inputs;
 const find=selector=>{if(!nodes.has(selector))nodes.set(selector,new Element());return nodes.get(selector);};
 editor.querySelector=find;root.querySelector=s=>s==='[data-local-editor]'?editor:find(s);
 let init,readTask,commitTask,eraseTask,calendarReady=false;
 let firstRead=true;
 const saved={revision:1,revisions:[{baseline_hash:base.baseline_hash,operation:'save',patch:{fields:{materials:{mode:'value',value:'合成已保存材料'}}}}]};
 const store={read(){if(initialFailure&&firstRead){firstRead=false;return Promise.reject(Error('STORAGE'));}if(initialFailure)return Promise.resolve(saved);return readTask?readTask.promise:Promise.resolve(null);},commit(){return commitTask.promise;},erase(){return eraseTask.promise;}};
 const window={confirm:()=>true,NkustActionCardStore:{createActionCardStore:()=>store},NkustCalendarUI:{setCard(){calendarReady=true;},setDirty(){calendarReady=false;}}};
 const document={querySelectorAll:()=>[root],createElement:()=>new Element(),addEventListener(_name,fn){init=fn;}};
 vm.runInNewContext(fs.readFileSync('app/static/web/action-card.js','utf8'),{window,document,structuredClone,Intl,Date,module:undefined});init();await tick();if(initialFailure){assert.equal(editor.hidden,false);assert.equal(calendarReady,false);await find('[data-refresh]').fire('click');await tick();assert.equal(calendarReady,true,'first successful retry must paint the saved card');assert.equal(inputs.find(x=>x.name==='materials.value').value,'合成已保存材料');return;}assert.equal(calendarReady,true,'initial saved card enables confirmation');
 assert.equal(find('[data-card-evidence="summary"]').children[0].children[2]?.textContent,'依據：來源摘要');
 commitTask=deferred();const resetting=find('[data-reset]').fire('click');await tick();assert.equal(calendarReady,false,'reset in flight must invalidate old export confirmation');
 commitTask.resolve({revision:1,revisions:[{baseline_hash:base.baseline_hash,operation:'reset'}]});await resetting;assert.equal(calendarReady,true,'successful reset paints and requires fresh confirmation');
 eraseTask=deferred();const erasing=find('[data-erase]').fire('click');await tick();assert.equal(calendarReady,false,'erase in flight must invalidate confirmation');eraseTask.resolve();await erasing;assert.equal(calendarReady,true);
 editor.hidden=true;readTask=deferred();const refreshing=find('[data-refresh]').fire('click');await tick();assert.equal(calendarReady,false,'explicit reread invalidates confirmation immediately');readTask.reject(Error('synthetic failure'));await refreshing;assert.equal(calendarReady,false,'failed reread cannot leave old export enabled');assert.equal(editor.hidden,false,'failed initial read must expose the secondary retry');assert.equal(editor.open,true);assert.equal(find('[data-save]').disabled,true,'unread saved state must not allow saving');
}
async function todoFallback(){
 const area=new Element(),body=new Element(),status=new Element();area.hasAttribute=n=>n==='data-todo-list';area.querySelector=s=>s==='[data-todo-status]'?status:s==='[data-todo-items]'?body:null;
 const record={source_ref:'synthetic',status:'active',effective_status:'active',deadline:null,deadline_group:'none',card:{source:{kind:'public',title:'合成待辦',url:null},fields:{action:{value:'請報名'}}}};
 let init;const document={querySelectorAll:()=>[area],createElement:()=>new Element(),addEventListener(_name,fn){init=fn;}};
 const window={NkustTodos:{createTodoStore:()=>({readAll:async()=>[record]}),projectTodo:r=>r,renderClockKey:()=>'',nextSnooze:()=>new Date().toISOString()},NkustCalendarUI:{mount(){throw Error('must not mount without calendar core');}}};
 const errors=[];
 process.on('unhandledRejection',capture);function capture(error){errors.push(error);}
 try{vm.runInNewContext(fs.readFileSync('app/static/web/todos.js','utf8'),{window,document,structuredClone,Intl,Date,URL,setInterval:()=>0});init();await tick();await tick();assert.equal(errors.length,0,'optional calendar failure must not crash todo list');assert.equal(body.children.length,1,'todo row must remain visible');assert.ok(body.children[0].children.some(n=>n.textContent==='行事曆匯出暫時無法使用；待辦仍可操作。'));}
 finally{process.removeListener('unhandledRejection',capture);}
}
(async()=>{if(process.argv[2]!=='fallback')await actionCardBoundary();await actionCardBoundary(true);await todoFallback();console.log('Calendar integration boundaries passed');})().catch(e=>{console.error(e);process.exitCode=1;});
