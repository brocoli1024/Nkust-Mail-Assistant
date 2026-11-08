const assert=require('node:assert/strict');
const {detectInstallContext,mount}=require('../app/static/web/install-guide.js');
function env(ua='iPhone Safari',standalone=false){return {navigator:{userAgent:ua,standalone,maxTouchPoints:0},matchMedia:()=>({matches:standalone})};}
assert.equal(detectInstallContext(env()).ios,true);
assert.equal(detectInstallContext(env('iPhone CriOS')).safari,false);
assert.equal(detectInstallContext({...env('Macintosh Safari'),navigator:{userAgent:'Macintosh Safari',maxTouchPoints:5}}).ios,true);
assert.equal(detectInstallContext(env('iPhone Safari',true)).standalone,true);
class Element {constructor(){this.handlers={};this.hidden=false;this.disabled=false;this.textContent='';}addEventListener(name,fn){this.handlers[name]=fn;}showModal(){this.open=true;}close(){this.open=false;}setAttribute(){} }
function fixture(environment){const nodes=Object.fromEntries(['open','dialog','close','native','status','ios','other','safari'].map(key=>[key,new Element()]));
const root={querySelector:selector=>nodes[selector.match(/data-install-([a-z]+)/)[1]]};const handlers={};environment.addEventListener=(name,fn)=>handlers[name]=fn;let saved=false;
mount({root,window:environment,storage:{setItem(){saved=true;}}});return {nodes,handlers,saved:()=>saved};}
(async()=>{
 const ios=fixture(env());assert.equal(ios.nodes.ios.hidden,false);assert.equal(ios.nodes.other.hidden,true);
 ios.nodes.open.handlers.click();assert.equal(ios.nodes.dialog.open,true);ios.nodes.close.handlers.click();assert.equal(ios.saved(),true);
 const installed=fixture(env('iPhone Safari',true));assert.equal(installed.nodes.open.disabled,true);assert.match(installed.nodes.open.textContent,/App模式/);
 const other=fixture(env('Chrome'));let prompted=0;other.handlers.beforeinstallprompt({preventDefault(){},prompt:async()=>{prompted++;},userChoice:Promise.resolve({outcome:'accepted'})});assert.equal(prompted,0);await other.nodes.native.handlers.click();assert.equal(prompted,1);assert.doesNotMatch(other.nodes.status.textContent,/已在App模式/);
 console.log('installation guide iPhone/iPad, standalone, gesture and fallback passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

const fs=require('node:fs');assert.match(fs.readFileSync('app/static/web/account.css','utf8'),/\.install-dialog \.button\.secondary \{color:var\(--ink\)/);
