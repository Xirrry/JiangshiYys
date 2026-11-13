import assert from 'node:assert/strict';
import {reportModel,reportPages,fileName} from './dojo/resources.js';
const role={id:'r',label:'测试角色',server:'一区'},meta={'200001':{name:'太阴符咒',kind:'realm_card',stars:1},'200002':{name:'太阴符咒',kind:'realm_card',stars:2}};
const rows=Array.from({length:31},(_,i)=>({role_id:'r',scope:'s',uid:'mail'+i,date:'2026-10-'+String(i+1).padStart(2,'0'),items:[[200001,79],[200002,49],[490001,2]],item_meta:meta,item_names:{'490001':'神秘的符咒'}}));
const model=reportModel([...rows,rows[0],{...rows[0],role_id:'other'}],role,'2026-10-01','2026-10-31');
assert.equal(model.mailCount,31);assert.equal(model.totals.find(r=>r.stars===1).n,2449);assert.equal(model.totals.find(r=>r.stars===2).n,1519);assert.equal(model.totals.find(r=>r.id===490001).n,62);assert.equal(model.details.length,93);const pages=reportPages(model,true);assert.equal(pages.length,1);assert.equal(pages[0].type,'long');assert.equal(pages[0].mails.length,31);assert.equal(pages[0].mails.flatMap(m=>m.items).length,93);assert.equal(reportPages(reportModel([],role,'2026-10-01','2026-10-31'),true).length,1);
assert.throws(()=>reportModel([...rows,{...rows[0],items:[[490001,99]]}],role,'2026-10-01','2026-10-31'));
assert.ok(!fileName('../测试:角色','月报','2026-10-01','2026-10-31',1,2).includes('/'));
console.log('PASS: role-scoped full-period totals, unique-mail deduplication, star separation, complete paginated daily resources, empty period and safe filenames');

const basic={...rows[0],uid:'base',type:400175,items:[[900016,99999]]};assert.equal(reportModel([...rows,basic],role,'2026-10-01','2026-10-31').mailCount,31);console.log('PASS: one complete mail-style long report, basic rewards excluded');

const {compactMailLayout,itemText}=await import('./dojo/mail-layout.js');
const mails=Array.from({length:14},(_,i)=>({date:'2026-11-'+String(9+Math.floor(i/2)).padStart(2,'0'),items:[{id:900001,name:'金币',n:82500},{id:490001,name:'神秘的符咒',n:6},{id:200001,name:'太阴符咒',stars:1,n:79},{id:200002,name:'太阴符咒',stars:2,n:49}]}));
const compact=compactMailLayout({totals:mails[0].items,mails});assert.equal(compact.groups.length,7);assert.equal(compact.groups.flatMap(g=>g.mails).length,14);assert.ok(compact.height<2300);assert.ok(compact.groups.every(g=>g.mails.length===2));
for(const group of compact.groups)for(const m of group.mails){assert.equal(m.lines.length,1);for(const token of m.lines.flat())assert.ok(token.x+token.width<=822);}
const longItem={name:'非常长的资源名称'.repeat(30),n:999999999};const wrapped=compactMailLayout({totals:[longItem],mails:[{date:'2026-11-11',items:[longItem]}]});assert.equal(wrapped.groups[0].mails[0].lines.flat().map(x=>x.text).join(''),itemText(longItem));
console.log('PASS: seven date groups preserve all 14 mails, compact text height, bounded wrapping, long resource names/numbers retained without ellipsis');
