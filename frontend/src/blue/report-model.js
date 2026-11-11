// Role-based adaptation of the web report model; no business associations.
export const shiftDay=(date,days)=>new Date(Date.parse(date+'T00:00:00Z')+days*86400000).toISOString().slice(0,10);
export function validDay(date){return typeof date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(date)&&Number.isFinite(Date.parse(date+'T00:00:00Z'))&&new Date(date+'T00:00:00Z').toISOString().slice(0,10)===date;}
export function weekRange(date){if(!validDay(date))return null;const day=new Date(date+'T00:00:00Z').getUTCDay(),from=shiftDay(date,-((day+6)%7));return {from,to:shiftDay(from,6)};}
export function monthRange(month){if(typeof month!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))return null;const from=month+'-01';if(!validDay(from))return null;const d=new Date(from+'T00:00:00Z');d.setUTCMonth(d.getUTCMonth()+1);return {from,to:shiftDay(d.toISOString().slice(0,10),-1)};}
export const attemptState=(r,field)=>r[field+'State']??(r[field]==null?'pending':'recorded');
export const blueComplete=r=>r.mode==='daily'?[r.first,r.second].every(v=>typeof v==='number'):[r.blue,r.fragments,r.eggs].every(v=>typeof v==='number');
export const bluePending=r=>r.mode==='daily'?['first','second'].some(f=>attemptState(r,f)==='pending'):!blueComplete(r);
export const blueKnown=r=>r.mode==='daily'?[r.first,r.second].some(v=>typeof v==='number'):typeof r.blue==='number';
export const blueTotal=r=>r.mode==='daily'?(r.first??0)+(r.second??0):(r.blue??0);
export function attemptText(r,field){const state=attemptState(r,field);return state==='not_played'?'未打':state==='unknown'?'未知':r[field]===null?'待补':String(r[field]);}
export function reportModel(role,records,from,to,today){
 if(!role||!role.id)throw Error('请先选择角色。');
 if(!validDay(from)||!validDay(to)||from>to)throw Error('请选择有效起止日期，开始不能晚于结束。');
 const days=Math.round((Date.parse(to)-Date.parse(from))/86400000)+1;if(days>366)throw Error('单次最多导出366个自然日，请分段导出。');
 const samples=records.filter(r=>r.mode==='daily'&&['first','second'].every(f=>attemptState(r,f)==='recorded'&&Number.isSafeInteger(r[f])&&r[f]>=0));
 const luckAverage=samples.length?samples.reduce((s,r)=>s+blueTotal(r),0)/samples.length:null;
 const own=records.filter(r=>r.role_id===role.id&&r.date>=from&&r.date<=to).sort((a,b)=>a.date.localeCompare(b.date));
 if(new Set(own.map(r=>r.date)).size!==own.length)throw Error('同角色同日存在重复记录，请先核对。');
 const map=new Map(own.map(r=>[r.date,r]));
 const rows=Array.from({length:days},(_,i)=>{const date=shiftDay(from,i),record=map.get(date);return {date,record,state:record?'recorded':date>today?'future':'missing'};});
 const known=own.filter(blueKnown),sum=list=>list.some(blueKnown)?list.reduce((s,r)=>s+blueTotal(r),0):null,x=own.filter(r=>r.mode==='xiajian');
 return {luckAverage,identity:{label:role.label,server:role.server||'未设区服'},from,to,rows,days,recorded:own.length,complete:own.filter(blueComplete).length,pending:own.filter(bluePending).length,unknown:own.reduce((s,r)=>s+(r.mode==='daily'?['first','second'].filter(f=>attemptState(r,f)==='unknown').length:0),0),missed:own.reduce((s,r)=>s+(r.mode==='daily'?['first','second'].filter(f=>attemptState(r,f)==='not_played').length:0),0),missing:rows.filter(r=>r.state==='missing').length,total:known.length?known.reduce((s,r)=>s+blueTotal(r),0):null,dojo:sum(own.filter(r=>r.mode==='daily')),xiajian:sum(x),fragments:x.some(r=>typeof r.fragments==='number')?x.reduce((s,r)=>s+(r.fragments??0),0):null,eggs:x.some(r=>typeof r.eggs==='number')?x.reduce((s,r)=>s+(r.eggs??0),0):null,needsReview:own.some(r=>r.date>today)};
}
export const reportFileName=(label,kind,from,to,page,count)=>`${String(label||'角色').replace(/[\\/:*?"<>|\u0000-\u001f]/g,'_').slice(0,40)}-${kind}-${from}至${to}${count>1?`-第${page}张`:''}.png`;
