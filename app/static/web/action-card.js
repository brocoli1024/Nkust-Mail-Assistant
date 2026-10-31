/* Personal display edits only: no source parsing, AI or network calls. */
(function(root){
'use strict';
const keys=['summary','action','audience','materials','deadline','event_date'];
const limits={summary:160,action:1200,audience:1200,materials:1200,deadline:10,event_date:10};
const object=x=>x!==null && typeof x==='object' && !Array.isArray(x);
function validateCorrectionPatch(raw){
  if(!object(raw)||Object.keys(raw).some(k=>!['fields','action_decision','deadline_kind'].includes(k))||!object(raw.fields||{}))throw Error('INVALID_PATCH');
  const out={fields:{},action_decision:raw.action_decision||'unknown',deadline_kind:raw.deadline_kind||'unknown'};
  if(!['yes','no','unknown'].includes(out.action_decision)||!['registration','application','submission','unknown'].includes(out.deadline_kind))throw Error('INVALID_PATCH');
  for(const [key,c] of Object.entries(raw.fields||{})){
    if(!keys.includes(key)||!object(c)||Object.keys(c).some(k=>!['mode','value','quote','confirmed'].includes(k))||!['inherit','value','pending'].includes(c.mode))throw Error('INVALID_PATCH');
    const change={mode:c.mode,value:c.value??null,quote:c.quote??null,confirmed:c.confirmed??false};
    if(typeof change.confirmed!=='boolean'||(change.quote!==null&&(typeof change.quote!=='string'||Array.from(change.quote).length>2000)))throw Error('INVALID_PATCH');
    if(c.mode!=='value'){
      if(change.value!==null||change.quote!==null||change.confirmed)throw Error('INVALID_PATCH');
    }else{
      if(typeof change.value!=='string'||!change.value.trim()||Array.from(change.value).length>limits[key])throw Error('INVALID_PATCH');
      if(['deadline','event_date'].includes(key)){
        const d=new Date(change.value+'T00:00:00Z');
        if(!/^\d{4}-\d{2}-\d{2}$/.test(change.value)||!change.confirmed||!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==change.value||change.value.startsWith('0000'))throw Error('INVALID_DATE');
      }
    }
    out.fields[key]=change;
  }
  return out;
}
function applyLocalPatch(card,raw){
  const patch=validateCorrectionPatch(raw),out=structuredClone(card);
  for(const [key,c] of Object.entries(patch.fields)){
    if(c.mode==='inherit')continue;
    const evidence=[];
    for(const [i,s] of (card.source.segments||[]).entries()){
      const at=c.quote?s.text.indexOf(c.quote):-1;
      if(at>=0)evidence.push({segment:i,quote:c.quote,start:Array.from(s.text.slice(0,at)).length,end:Array.from(s.text.slice(0,at)).length+Array.from(c.quote).length,role:key,year_inferred:false});
    }
    out.fields[key]={value:c.mode==='value'?c.value:null,state:c.mode==='value'?'user_confirmed':'pending',origin:'user',evidence,
      warnings:c.quote&&!evidence.length?['個人補充，系統未驗證來源']:[]};
    if(key==='action')out.requires_action=c.mode==='value'?({yes:true,no:false,unknown:null})[patch.action_decision]:null;
    if(key==='deadline')out.deadline_kind=c.mode==='value'?patch.deadline_kind:'unknown';
  }
  return out;
}
function formatLocalHistory(record){return record?JSON.stringify({baselines:record.baselines,revisions:record.revisions},null,2):'尚無紀錄';}
const api={validateCorrectionPatch,applyLocalPatch,formatLocalHistory};root.NkustActionCards=api;
if(typeof module!=='undefined')module.exports=api;
if(typeof document==='undefined')return;
function init(){
  for(const node of document.querySelectorAll('[data-card-payload]')){
    let payload;try{payload=JSON.parse(node.dataset.cardPayload);}catch{continue;}
    if(!['public','demo'].includes(payload.scope))continue;
    const base=payload.base_card,editor=node.querySelector('[data-local-editor]'),status=node.querySelector('[data-correction-status]');
    if(!editor)continue;
    let record=null,expected=0,ready=false,store=null;
    const message=text=>{status.textContent=text;};
    const invalidate=reason=>{root.NkustCalendarUI?.setDirty(node,reason);root.NkustTodoUI?.setDirty(node);};
    const control=name=>Array.from(editor.querySelectorAll('[name]')).find(e=>e.name===name);
    const fill=patch=>{
      for(const key of keys){const c=patch?.fields?.[key];control(key+'.mode').value=c?.mode||'inherit';control(key+'.value').value=c?.value||'';control(key+'.quote').value=c?.quote||'';const check=control(key+'.confirmed');if(check)check.checked=!!c?.confirmed;}
      control('action_decision').value=patch?.action_decision||'unknown';control('deadline_kind').value=patch?.deadline_kind||'unknown';
    };
    const paint=card=>{
      for(const key of keys){const f=card.fields[key];
        const box=node.querySelector('[data-card-evidence="'+key+'"]');box.replaceChildren();
        if(f.evidence?.length){const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent='查看依據';detail.append(summary);for(const e of f.evidence){const quote=document.createElement('blockquote');quote.textContent=e.quote;detail.append(quote);const label=document.createElement('p');label.textContent='依據：'+({title:'來源標題',excerpt:'來源摘要',original:'郵件公告原文'}[card.source.segments?.[e.segment]?.kind]||'來源待確認');detail.append(label);}box.append(detail);}
        const warnings=node.querySelector('[data-card-warnings="'+key+'"]');warnings.replaceChildren();for(const text of f.warnings||[]){const p=document.createElement('p');p.textContent=text;warnings.append(p);}
        node.querySelector('[data-card-field="'+key+'"]').textContent=f.value||'待確認';node.querySelector('[data-card-state="'+key+'"]').textContent=f.origin==='user'?'我的修正 · '+(f.state==='pending'?'待確認':'使用者確認，非系統驗證'):(f.state==='pending'?'待確認':'來源規則辨識');}
      root.NkustTodoUI?.setCard(node,card);
      root.NkustCalendarUI?.setCard(node,card);
      const d=card.fields.deadline;node.querySelector('[data-deadline-passed]').hidden=!(d.value&&['supported','user_confirmed'].includes(d.state)&&d.value<payload.taipei_today);
    };
    function render(){
      const latest=record?.revisions?.at(-1),same=latest?.baseline_hash===base.baseline_hash;
      const patch=same&&latest.operation==='save'?latest.patch:null;
      paint(patch?applyLocalPatch(base,patch):base);fill(patch);
      node.querySelector('[data-local-history]').textContent=formatLocalHistory(record);
      if(latest&&!same)message('來源或解析版本已變更，舊修正未套用，請重新核對後儲存。');
    }
    async function load(preserveInputs=false){
      ready=false;invalidate('正在重新讀取修正，先前的匯出確認已取消；請完成核對後再確認。');
      try{
        if(payload.scope==='public'){store=root.NkustActionCardStore.createActionCardStore();record=await store.read(base.source.source_ref);}
        expected=record?.revision||0;if(!preserveInputs)render();else{node.querySelector('[data-local-history]').textContent=formatLocalHistory(record);message('已讀取裝置最新版本，輸入仍保留，請核對歷史後再儲存。');}ready=true;editor.hidden=false;
      }catch(e){invalidate('修正讀取失敗，無法確認目前版本，匯出已停用；請重新載入頁面核對。');message('無法讀取裝置修正，尚未清除既有資料。請重新載入重試。');}
    }
    function readPatch(){
      const fields={};for(const key of keys){const mode=control(key+'.mode').value;fields[key]={mode};if(mode==='value')fields[key]={mode,value:control(key+'.value').value,quote:control(key+'.quote').value||null,confirmed:!!control(key+'.confirmed')?.checked};}
      return validateCorrectionPatch({fields,action_decision:control('action_decision').value,deadline_kind:control('deadline_kind').value});
    }
    async function commit(operation){
      if(!ready)return;
      invalidate('正在更新修正，先前的匯出確認已取消；成功後請重新核對。');
      try{
        const patch=operation==='save'?readPatch():null;
        ready=false;message('正在儲存，請稍候。');
        if(payload.scope==='public')record=await store.commit({card:base,patch,operation,expectedRevision:expected});
        else{record=record||{schema_version:1,source_ref:base.source.source_ref,revision:0,baselines:{},revisions:[]};record.baselines[base.baseline_hash]=base;record.revision++;record.revisions.push({revision:record.revision,baseline_hash:base.baseline_hash,operation,patch:patch||{fields:{}},created_at:new Date().toISOString()});}
        expected=record.revision;render();message(payload.scope==='demo'?'示範修正已更新；重新載入會重設。':'已保存至此裝置（裝置記錄時間：'+new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',dateStyle:'short',timeStyle:'short'}).format(new Date())+'）。');
      }catch(e){editor.open=true;message(e.message==='REVISION_CONFLICT'?'其他分頁已更新，本次未儲存；請先重新讀取裝置版本並核對，輸入仍保留。':'尚未儲存：請核對日期、確認欄、字數或裝置儲存空間，輸入仍保留。');}
      finally{ready=true;}
    }
    const refresh=node.querySelector('[data-refresh]');if(payload.scope==='public'){refresh.hidden=false;refresh.addEventListener('click',()=>load(!editor.hidden));}
    editor.addEventListener('input',()=>{message('有尚未儲存的修正。');root.NkustTodoUI?.setDirty(node);root.NkustCalendarUI?.setDirty(node);});
    editor.querySelector('[data-save]').addEventListener('click',()=>commit('save'));
    editor.querySelector('[data-reset]').addEventListener('click',()=>commit('reset'));
    editor.querySelector('[data-erase]')?.addEventListener('click',async()=>{
      if(!ready||!root.confirm('永久刪除此公告在此裝置的修正歷史？不影響公開公告。'))return;
      ready=false;invalidate('正在刪除裝置修正，先前匯出確認已取消；完成後請重新核對。');
      try{await store.erase(base.source.source_ref,expected);record=null;expected=0;render();message('此公告的裝置修正已刪除。');}catch{invalidate('無法確認修正刪除結果，匯出已停用；請重新載入頁面核對。');message('未能刪除；可能已有其他分頁更新，請重新載入核對。');}finally{ready=true;}
    });
    load();
  }
}
document.addEventListener('DOMContentLoaded',init);
})(typeof window!=='undefined'?window:globalThis);
