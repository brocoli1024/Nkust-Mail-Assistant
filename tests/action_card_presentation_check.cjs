const assert=require('node:assert/strict');
const {fieldDisplay,applyLocalPatch}=require('../app/static/web/action-card.js');
const c={source:{kind:'public',segments:[{kind:'official_text',text:'活動日期：2026年10月31日'}],metadata:{article:{text:true}}},candidates:[{role:'event_date',segment:0}],fields:{deadline:{value:null,state:'pending',origin:'rule',evidence:[]}}};
assert.equal(fieldDisplay(c,'deadline').value,'本文未找到截止說明');
c.source.metadata={};assert.equal(fieldDisplay(c,'deadline').value,'尚待讀取完整原文');
c.source.metadata={article:{text:true}};c.fields.deadline.evidence=[{quote:'截止日期待公告'}];assert.equal(fieldDisplay(c,'deadline').value,'資訊待核對');
c.fields.deadline={value:'2026-11-01',state:'user_confirmed',origin:'user'};assert.match(fieldDisplay(c,'deadline').state,/使用者確認/);
console.log('Action card presentation contracts passed');
