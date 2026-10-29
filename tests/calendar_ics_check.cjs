'use strict';
const assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const {buildCalendar,foldLine,escapeText,taipeiToUTC,projectCard}=require('../app/static/web/calendar-ics.js');
const payload={schema_version:1,source:{kind:'public',source_ref:'synthetic-source',title:'合成校園活動',url:'https://www.nkust.edu.tw/p/422-1000-1001.php'},baseline_hash:'a'.repeat(64),summary:'來源摘要',action:'請報名',dates:{event_date:{value:'2026-11-20',state:'supported',evidence:['活動日期：2026年11月20日']},deadline:{value:'2026-11-10',state:'user_confirmed',evidence:[]}},time_status:'unknown',context:'current'};
const choose={kind:'event_date',mode:'all_day',confirmed:true};
const options={now:new Date('2026-10-29T16:00:00Z'),crypto:webcrypto};
const unfold=text=>text.replace(/\r\n[ \t]/g,'');
const prop=(text,key)=>unfold(text).split('\r\n').find(l=>l.startsWith(key+':'))?.slice(key.length+1);
(async()=>{
 const event=await buildCalendar(payload,choose,options),deadline=await buildCalendar(payload,{...choose,kind:'deadline'},options);
 assert.match(event.text,/DTSTART;VALUE=DATE:20261120\r\n/);assert.match(event.text,/DTEND;VALUE=DATE:20261121\r\n/);
 assert.match(deadline.text,/DTSTART;VALUE=DATE:20261110/);assert.notEqual(prop(event.text,'UID'),prop(deadline.text,'UID'));
 assert.equal(prop(event.text,'UID'),prop((await buildCalendar(payload,choose,{...options,now:new Date('2027-01-01Z')})).text,'UID'));
 assert.equal(prop(event.text,'DTSTAMP'),'20261029T160000Z');assert.ok(event.text.endsWith('END:VCALENDAR\r\n'));
 assert.ok(!/(?<!\r)\n/.test(event.text));assert.ok(event.text.split('\r\n').every(l=>Buffer.byteLength(l,'utf8')<=75));
 assert.match(event.text,/URL:https:\/\/www.nkust.edu.tw/);
 for(const [value,end] of [['2024-02-29','20240301'],['2026-12-31','20270101']]){const p=structuredClone(payload);p.dates.event_date.value=value;assert.match((await buildCalendar(p,choose,options)).text,new RegExp('DTEND;VALUE=DATE:'+end));}
 for(const date of ['2026-02-30','2026-1-1','0000-01-01','9999-12-31']){const p=structuredClone(payload);p.dates.event_date.value=date;await assert.rejects(buildCalendar(p,choose,options));}
 for(const state of ['pending','stale']){const p=structuredClone(payload);p.dates.event_date.state=state;await assert.rejects(buildCalendar(p,choose,options),/DATE_PENDING/);}
 for(const confirmed of [false,'true',1])await assert.rejects(buildCalendar(payload,{...choose,confirmed},options),/CONFIRM/);
 await assert.rejects(buildCalendar(payload,{...choose,kind:'both'},options));
 const timed=await buildCalendar(payload,{...choose,mode:'timed',startTime:'00:30',endDateTime:'2026-11-20T01:30'},options);
 assert.match(timed.text,/DTSTART:20261119T163000Z/);assert.match(timed.text,/DTEND:20261119T173000Z/);assert.ok(!timed.text.includes('DTSTART;TZID'));
 const noEnd=await buildCalendar(payload,{...choose,mode:'timed',startTime:'09:00'},options);assert.ok(!noEnd.text.includes('DTEND'));assert.match(unfold(noEnd.text),/Asia\/Taipei/);
 for(const startTime of ['24:00','09:60','9:00',''])await assert.rejects(buildCalendar(payload,{...choose,mode:'timed',startTime},options));
 await assert.rejects(buildCalendar(payload,{...choose,mode:'timed',startTime:'09:00',endDateTime:'2026-11-20T08:59'},options),/END/);
 assert.equal(taipeiToUTC('2026-01-01','00:30').toISOString(),'2025-12-31T16:30:00.000Z');
 assert.throws(()=>taipeiToUTC('1979-07-01','00:30'),/TIME_NOT_UNIQUE/);
 assert.throws(()=>taipeiToUTC('1979-09-30','23:30'),/TIME_NOT_UNIQUE/);
 const unsafe=structuredClone(payload);unsafe.source.title='公告😀\\,;\r\nBEGIN:VEVENT';unsafe.summary='字😀'.repeat(100);unsafe.source.url='https://www.nkust.edu.tw/\r\nATTENDEE:bad';
 const text=(await buildCalendar(unsafe,choose,options)).text;
 assert.equal((text.match(/(?:^|\r\n)BEGIN:VEVENT/g)||[]).length,1);assert.ok(!text.includes('\r\nATTENDEE:'));assert.ok(!text.includes('\r\nURL:'));
 assert.match(prop(text,'SUMMARY'),/\\nBEGIN:VEVENT/);assert.ok(text.split('\r\n').every(l=>Buffer.byteLength(l)<=75));
 const line='DESCRIPTION:'+('😀校園通知\\n'.repeat(50));assert.equal(foldLine(line).replace(/\r\n /g,''),line);assert.equal(escapeText('a\\b,c;d\r\ne'),'a\\\\b\\,c\\;d\\ne');
 const privateP=structuredClone(payload);privateP.source.kind='private';privateP.source.source_ref='secret-internal-email-id';const privateFile=await buildCalendar(privateP,choose,options);assert.match(privateFile.text,/CLASS:PRIVATE/);assert.ok(!privateFile.text.includes('secret-internal-email-id'));assert.match(privateFile.filename,/private/);
 const demo=await buildCalendar({...payload,source:{...payload.source,kind:'demo'}},choose,options);assert.match(demo.filename,/demo/);assert.match(unfold(demo.text),/合成示範/);
 await assert.rejects(buildCalendar(payload,choose,{...options,crypto:null}),/CRYPTO/);
 const projected=projectCard({source:{...payload.source,segments:[{text:'secret entire original'}]},baseline_hash:payload.baseline_hash,fields:{summary:{value:'摘要'},action:{value:'行動'},deadline:payload.dates.deadline,event_date:payload.dates.event_date},time_status:'unknown'},{snapshot:true});
 assert.equal(projected.context,'snapshot');assert.ok(!JSON.stringify(projected).includes('secret entire original'));
 console.log('Calendar ICS contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
