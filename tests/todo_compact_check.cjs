const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element{
 constructor(tag,text){this.tag=tag;this.textContent=text||'';this.children=[];this.handlers={};this.dataset={};this.hidden=false;}
 append(...nodes){this.children.push(...nodes);for(const n of nodes)n.parent=this;}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);}
 get lastElementChild(){return this.children.at(-1);}
 addEventListener(name,fn){this.handlers[name]=fn;}
 hasAttribute(name){return ['data-device-todo','data-compact'].includes(name);}
 closest(){return cardNode;}
 querySelector(s){return s==='[data-todo-status]'?status:s==='[data-todo-actions]'?body:null;}
}
const status=new Element('p'),body=new Element('div'),area=new Element('section'),cardNode={};
area.dataset={scope:'public'};area.append(body,status);
let onReady,readFails=true,writeFails=false,changes=0,records=[];
const store={async readAll(){if(readFails)throw Error('STORAGE');return records;},async change(o){changes++;if(writeFails)throw Error('REVISION_CONFLICT');records=[{source_ref:o.sourceRef,card:o.card,status:'active',effective_status:'active',revision:1}];}};
const root={NkustTodos:{createTodoStore:()=>store,projectTodo:r=>r,renderClockKey:()=>'',nextSnooze:()=>''},confirm:()=>true};
const doc={querySelectorAll:()=>[area],createElement:tag=>new Element(tag),addEventListener:(_,fn)=>onReady=fn};
vm.runInNewContext(fs.readFileSync('app/static/web/todos.js','utf8'),{window:root,document:doc,structuredClone,WeakMap,Date,Intl,setInterval:()=>{}});
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 onReady();await tick();
 const help=area.children.find(n=>n.tag==='details');assert.equal(help.open,true,'read failure must expose error and retry');assert.match(status.textContent,/讀取失敗/);
 readFails=false;await help.children.find(n=>n.tag==='button').handlers.click();await tick();
 const card={source:{source_ref:'public:1'},baseline_hash:'v1'};
 root.NkustTodoUI.setCard(cardNode,card);assert.equal(body.children[0].disabled,false);
 root.NkustTodoUI.setDirty(cardNode);assert.equal(body.children[0].disabled,true);await body.children[0].handlers.click();assert.equal(changes,0);
 root.NkustTodoUI.setCard(cardNode,card);help.open=false;writeFails=true;await body.children[0].handlers.click();await tick();assert.equal(help.open,true,'write conflict must expose recovery');assert.match(status.textContent,/其他頁面已更新/);
 writeFails=false;await help.children.find(n=>n.tag==='button').handlers.click();await tick();await body.children[0].handlers.click();await tick();assert.equal(body.children.at(-1).textContent,'查看我的待辦');assert.equal(records[0].source_ref,'public:1');
 console.log('Compact todo dirty, storage error, conflict and save contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});