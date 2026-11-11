// Local-only desktop adapter. No business endpoints or seeded data.
let blueSnapshot=null,blueIds=[],blueBusy=false,blueEditing=false,blueDirty=false,blueInitialForm='',blueExportPage=0,blueExportRows=[];
const blueNotify=text=>{$('status').textContent=text;};
const blueMessage=dirty=>{blueDirty=dirty;window.parent.postMessage({type:'launcher-blue-dirty',dirty},window.parent.location.origin);};
const blueForm=()=>JSON.stringify([...new FormData($('entry-form')).entries()]);
function blueDirtyCheck(){blueMessage(blueEditing&&blueForm()!==blueInitialForm);}
async function blueCall(action,payload={}){const api=window.parent.pywebview?.api;if(!api?.blue_records)throw Error('本机蓝票服务尚未就绪，请刷新');const response=await api.blue_records(action,payload);if(!response.ok)throw Error(response.error||'蓝票操作失败');return response.data;}
function blueWorking(value){blueBusy=value;for(const id of ['blue-subjects','blue-refresh','blue-export'])$(id).disabled=value;$('entry-form').classList.toggle('blue-save-busy',value);}
const originalRender=render;
render=function(){
 if(!names.length){$('content').hidden=false;$('statistics-view').hidden=true;$('record').disabled=true;$('scope').textContent='尚未选择参与角色';$('content').innerHTML='<div class="blue-empty">尚无参与角色或可查看的历史。<br>点击上方“选择参与角色”，只勾选你需要记录的角色。</div>';return;}
 originalRender();
};
function blueApply(data){
 const previous=blueIds[Number($('character').value)],calendarId=blueIds[calendarCharacter];blueSnapshot=data;
 const visible=data.roles.filter(r=>r.selected||($('blue-history-roles').checked&&r.has_records));
 names.splice(0,names.length,...visible.map(r=>r.label+(r.server?' · '+r.server:'')+(!r.selected?'（历史）':'')));
 blueIds=visible.map(r=>r.id);records.clear();
 for(const r of data.records){const n=blueIds.indexOf(r.role_id);if(n>=0)records.set(keyFor(r.date,n,r.mode),{...r,n});}
 $('character').replaceChildren(new Option('全部角色','all'));names.forEach((n,i)=>$('character').add(new Option(n,String(i))));
 if(previous&&blueIds.includes(previous))$('character').value=String(blueIds.indexOf(previous));calendarCharacter=Math.max(0,blueIds.indexOf(calendarId));
 $('blue-participants').textContent=`参与 ${data.roles.filter(r=>r.selected).length} 个 · 历史 ${data.roles.filter(r=>!r.selected&&r.has_records).length} 个`;
 render();
}
async function blueLoad(){if(blueBusy)return;if(blueEditing){blueNotify('请先保存或关闭正在编辑的记录');return;}blueWorking(true);try{blueApply(await blueCall('load'));blueNotify('');}catch(e){blueNotify(e.message);}finally{blueWorking(false);}}
const blueOpenEditor=openEditor;
openEditor=function(date,ns=selectedNames(),mode){
 if(blueBusy)return;if(!blueSnapshot){blueNotify('请先载入本机数据');return;}
 const writable=ns.filter(n=>blueSnapshot.roles.some(r=>r.id===blueIds[n]&&r.active&&r.selected));
 if(!writable.length){if(ns.length===1){blueShowHistory(blueIds[ns[0]],date);return;}blueNotify('请选择参与记录的角色；历史角色仅供查看');return;}
 if(date>localToday()){blueNotify('不能记录未来掉落');return;}
 weekStart=monday(date);blueOpenEditor(date,writable,mode);blueEditing=true;blueInitialForm=blueForm();blueMessage(false);
 for(const table of ['edit-rows','xiajian-edit-rows'])[...$(table).rows].forEach((tr,i)=>{const b=document.createElement('button');b.type='button';b.className='secondary history-button';b.textContent='修改历史';const id=blueIds[writable[i]];b.onclick=()=>blueShowHistory(id,date);tr.cells[0].append(document.createElement('br'),b);});
};
const blueCloseEditor=closeEditor;
closeEditor=function(force=false){if(blueBusy)return;if(!force&&blueDirty&&!confirm('当前记录尚未保存，放弃修改？'))return;blueCloseEditor();blueEditing=false;blueMessage(false);};
window.__blueCanLeave=()=>{if(blueBusy){blueNotify('正在保存或导出，请稍后再切换');return false;}if(blueEditing){closeEditor();return !blueEditing;}return true;};
$('entry-form').addEventListener('input',blueDirtyCheck);$('entry-form').addEventListener('change',()=>queueMicrotask(blueDirtyCheck));
$('entry-form').onsubmit=async event=>{
 event.preventDefault();if(blueBusy||!blueSnapshot)return;
 const form=new FormData(event.target),mode=$('editor-kind').value,rows=[];let removals=0;
 try{
  for(const n of editingNames){
   const parse=field=>{const raw=String(form.get(`${field}-${n}`)??'').trim();if(raw==='')return null;const value=Number(raw);if(!Number.isSafeInteger(value)||value<0||value>1000000)throw Error('数量必须为 0–1000000 的整数');return value;};
   const first=mode==='daily'?readAttempt(form,n,'first'):{value:null,state:'pending'},second=mode==='daily'?readAttempt(form,n,'second'):{value:null,state:'pending'};
   const row={role_id:blueIds[n],date:selectedDate,mode,first:first.value,second:second.value,firstState:first.state,secondState:second.state,blue:mode==='xiajian'?parse('blue'):null,fragments:mode==='xiajian'?parse('fragments'):null,eggs:mode==='xiajian'?parse('eggs'):null,note:String(form.get(`${mode==='daily'?'':'x-'}note-${n}`)??'').trim()};
   const empty=isEmpty({...row,n});const existing=records.get(keyFor(selectedDate,n,mode));
   if(empty&&!existing)continue;
   if(empty){row.remove=true;removals++;}
   rows.push(row);
  }
  if(!rows.length){$('error').textContent='请填写数量（含 0）、备注，或明确标记未打 / 未知；空白不保存为零。';return;}
  if(removals&&!confirm(`有 ${removals} 条已有记录被清空，确认撤销？历史仍保留。`))return;
  const replacement=$('confirm-replace')?.checked===true;
  const conflicts=rows.some(r=>!r.remove&&records.has(keyFor(r.date,blueIds.indexOf(r.role_id),r.mode==='daily'?'xiajian':'daily')));
  if(conflicts&&!replacement){$('error').textContent='请勾选确认替换已有来源后再保存';return;}
  blueWorking(true);const top=scrollY;const saved=await blueCall('save',{rows,revision:blueSnapshot.revision,allow_replace:replacement});
  blueWorking(false);closeEditor(true);blueApply(saved);blueNotify('已保存到本机，修改历史已记录');requestAnimationFrame(()=>scrollTo(0,top));
 }catch(e){$('error').textContent=e.message;}finally{blueWorking(false);}
};
const roleDialog=document.createElement('dialog');roleDialog.id='blue-role-dialog';roleDialog.setAttribute('aria-label','选择参与蓝票记录的角色');roleDialog.innerHTML='<h2>选择参与角色</h2><p>只勾选需要记录的角色；退出名单不清除历史，不影响任何启动方案。</p><input id="blue-role-search" placeholder="搜索昵称或区服" aria-label="搜索参与角色"><div class="blue-tools"><button id="blue-pick-visible" class="secondary">选择当前搜索结果</button><button id="blue-clear-picks" class="secondary">清空选择</button></div><div class="blue-roles" id="blue-role-options"></div><p class="error" id="blue-role-error"></p><div class="actions"><button id="blue-role-cancel" class="secondary">取消</button><button id="blue-role-save">保存参与名单</button></div>';document.body.append(roleDialog);
function blueFilterRoles(){const q=$('blue-role-search').value.trim().toLowerCase();for(const label of $('blue-role-options').children)label.hidden=!label.textContent.toLowerCase().includes(q);}
$('blue-subjects').onclick=()=>{if(blueBusy||blueEditing||!blueSnapshot){blueNotify('请先关闭编辑或刷新数据');return;}$('blue-role-options').innerHTML=blueSnapshot.roles.filter(r=>r.active).map(r=>`<label><input type="checkbox" value="${esc(r.id)}" ${r.selected?'checked':''}><span>${esc(r.label)}<small>${esc(r.server||'未填写区服')}</small></span></label>`).join('');$('blue-role-search').value='';$('blue-role-error').textContent='';roleDialog.showModal();};
$('blue-role-search').oninput=blueFilterRoles;
$('blue-pick-visible').onclick=()=>{for(const label of $('blue-role-options').children)if(!label.hidden)label.querySelector('input').checked=true;};
$('blue-clear-picks').onclick=()=>{$('blue-role-options').querySelectorAll('input').forEach(i=>i.checked=false);};
$('blue-role-cancel').onclick=()=>{if(!blueBusy)roleDialog.close();};
$('blue-role-save').onclick=async()=>{if(blueBusy)return;blueWorking(true);try{const ids=[...$('blue-role-options').querySelectorAll('input:checked')].map(i=>i.value);const next=await blueCall('subjects',{ids,revision:blueSnapshot.revision});blueApply(next);roleDialog.close();blueNotify('参与名单已保存；未参与的角色不会计入漏记或零掉落');}catch(e){$('blue-role-error').textContent=e.message;}finally{blueWorking(false);}};
const historyDialog=document.createElement('dialog');historyDialog.id='blue-record-history';historyDialog.setAttribute('aria-label','蓝票修改历史');historyDialog.innerHTML='<h2>修改历史</h2><div id="blue-history-content"></div><div class="actions"><button id="blue-history-close" class="secondary">关闭</button></div>';document.body.append(historyDialog);$('blue-history-close').onclick=()=>historyDialog.close();
function blueRecordText(r){if(!r)return '无记录';const value=(f)=>r[f]===null?(r[f+'State']==='not_played'?'未打':r[f+'State']==='unknown'?'未知':'待补'):r[f];return (r.mode==='daily'?`道馆 ${value('first')} + ${value('second')}`:`狭间 蓝票 ${r.blue??'待补'} / 黑碎 ${r.fragments??'待补'} / 黑蛋 ${r.eggs??'待补'}`)+(r.note?' · '+r.note:'');}
async function blueShowHistory(id,date){if(blueBusy)return;historyDialog.showModal();$('blue-history-content').textContent='正在读取…';try{const list=await blueCall('history',{role_id:id,date});$('blue-history-content').innerHTML=`<p>${esc(date)} · 最近 100 次修改</p>`+(list.length?'<div class="table-wrap"><table><thead><tr><th>时间</th><th>修改前</th><th>修改后</th></tr></thead><tbody>'+list.map(h=>`<tr><td>${esc(h.changed_at)}</td><td>${esc(blueRecordText(JSON.parse(h.before_json)))}</td><td>${esc(blueRecordText(JSON.parse(h.after_json)))}</td></tr>`).join('')+'</tbody></table></div>':'<p>暂无修改历史</p>');}catch(e){$('blue-history-content').textContent=e.message;}}
$('blue-history-roles').onchange=()=>{if(blueEditing){$('blue-history-roles').checked=!$('blue-history-roles').checked;blueNotify('请先保存或关闭编辑');return;}if(blueSnapshot)blueApply(blueSnapshot);};
$('blue-refresh').onclick=blueLoad;
// Export only the current chosen roles/date scope. No hidden launcher configuration.
const exportDialog=document.createElement('dialog');exportDialog.id='blue-export-dialog';exportDialog.setAttribute('aria-label','导出蓝票记录');exportDialog.innerHTML='<h2>导出蓝票记录</h2><p>导出当前角色筛选及月份、周或统计范围；不含账号凭证。</p><div class="blue-export-controls"><button id="blue-export-csv">导出 CSV</button><button id="blue-export-json" class="secondary">导出 JSON</button><button id="blue-export-png">下载当前页 PNG</button><button id="blue-export-prev" class="secondary">上一页</button><span id="blue-export-pages"></span><button id="blue-export-next" class="secondary">下一页</button></div><p id="blue-export-error" class="error"></p><canvas id="blue-report-canvas" class="blue-export-preview"></canvas><div class="actions"><button id="blue-export-close" class="secondary">关闭</button></div>';document.body.append(exportDialog);$('blue-export-close').onclick=()=>{if(!blueBusy)exportDialog.close();};
function blueExportSelection(){let list=location.hash==='#statistics'?statsRows():rows();if(location.hash!=='#statistics'&&view==='week'){const dates=Array.from({length:7},(_,i)=>shiftDate(weekStart,i));list=list.filter(r=>dates.includes(r.date));}if(location.hash!=='#statistics'&&view==='calendar'&&calendarMode==='period')list=[...records.values()].filter(r=>r.n===calendarCharacter&&r.date>=periodFrom&&r.date<=periodTo);return [...list].sort((a,b)=>a.date.localeCompare(b.date)||a.n-b.n);}
function blueExportData(){return blueExportRows.map(r=>({role:blueSnapshot.roles.find(v=>v.id===blueIds[r.n])?.label||'',server:blueSnapshot.roles.find(v=>v.id===blueIds[r.n])?.server||'',date:r.date,mode:r.mode,first:r.first,firstState:r.firstState,second:r.second,secondState:r.secondState,blue:r.blue,fragments:r.fragments,eggs:r.eggs,note:r.note}));}
function blueDrawReport(){const items=blueExportData(),pages=Math.max(1,Math.ceil(items.length/30));blueExportPage=Math.max(0,Math.min(blueExportPage,pages-1));const slice=items.slice(blueExportPage*30,(blueExportPage+1)*30);const canvas=$('blue-report-canvas');canvas.width=1800;canvas.height=340+slice.length*78;const ctx=canvas.getContext('2d');ctx.fillStyle='#f7f1e5';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#473929';ctx.font='bold 44px "Microsoft YaHei UI"';ctx.fillText('蓝票产出记录',65,85);ctx.font='24px "Microsoft YaHei UI"';ctx.fillText(`已知蓝票 ${blueSum(blueExportRows)} 张 · 黑碎 ${rewardSum(blueExportRows,'fragments')} 片 · 黑蛋 ${rewardSum(blueExportRows,'eggs')} 个`,65,135);ctx.fillStyle='#8e7d68';ctx.fillText(`仅汇总已知数量，空白不当作 0 · 第 ${blueExportPage+1} / ${pages} 页`,65,178);ctx.fillStyle='#473929';ctx.fillText('日期',65,240);ctx.fillText('角色 / 区服',270,240);ctx.fillText('掉落与备注',760,240);ctx.font='23px "Microsoft YaHei UI"';slice.forEach((r,i)=>{const y=285+i*78;ctx.strokeStyle='#ddcfb7';ctx.beginPath();ctx.moveTo(65,y+48);ctx.lineTo(1735,y+48);ctx.stroke();ctx.fillStyle='#473929';ctx.fillText(r.date,65,y);ctx.fillText(r.role.slice(0,18),270,y);ctx.fillStyle='#8e7d68';ctx.fillText(r.server.slice(0,20),270,y+29);ctx.fillStyle='#473929';ctx.fillText(blueRecordText(r).slice(0,58),760,y);});$('blue-export-pages').textContent=`${blueExportPage+1} / ${pages}`;$('blue-export-prev').disabled=blueExportPage===0;$('blue-export-next').disabled=blueExportPage===pages-1;}
window.__blueOpenDataExport=()=>{if(blueBusy||blueEditing)return;blueExportRows=blueExportSelection();blueExportPage=0;$('blue-export-error').textContent='';blueDrawReport();exportDialog.showModal();};
$('blue-export-prev').onclick=()=>{blueExportPage--;blueDrawReport();};$('blue-export-next').onclick=()=>{blueExportPage++;blueDrawReport();};
async function blueExport(kind){if(blueBusy)return;blueWorking(true);try{const data=blueExportData();let content;if(kind==='png')content=$('blue-report-canvas').toDataURL('image/png').split(',')[1];else if(kind==='json')content=JSON.stringify({format:'launcher-blue-export-v1',exported_at:new Date().toISOString(),records:data},null,2);else{const headers=['role','server','date','mode','first','firstState','second','secondState','blue','fragments','eggs','note'];const quote=v=>{let text=v==null?'':String(v);if(/^[=+\-@\t\r]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};content=[headers,...data.map(r=>headers.map(k=>r[k]))].map(row=>row.map(quote).join(',')).join('\r\n');}const result=await window.parent.pywebview.api.blue_export({kind,content});if(!result.ok)throw Error(result.error);$('blue-export-error').textContent=result.data.cancelled?'已取消导出':'导出完成';}catch(e){$('blue-export-error').textContent=e.message;}finally{blueWorking(false);}}
for(const kind of ['csv','json','png'])$('blue-export-'+kind).onclick=()=>blueExport(kind);
window.addEventListener('hashchange',render);
$('month').value=localToday().slice(0,7);$('stats-from').value=localToday().slice(0,7)+'-01';$('stats-to').value=localToday();
blueLoad();

$('close').onclick=()=>closeEditor();$('cancel').onclick=()=>closeEditor();$('editor').oncancel=e=>{e.preventDefault();closeEditor();};
const blueBaseCanLeave=window.__blueCanLeave;window.__blueCanLeave=()=>{if(!blueBaseCanLeave())return false;if(roleDialog.open){const chosen=[...$('blue-role-options').querySelectorAll('input:checked')].map(i=>i.value).sort().join('/'),saved=blueSnapshot.roles.filter(r=>r.selected&&r.active).map(r=>r.id).sort().join('/');if(chosen!==saved&&!confirm('参与名单尚未保存，放弃修改？'))return false;roleDialog.close();}if(historyDialog.open)historyDialog.close();if(exportDialog.open)exportDialog.close();return true;};

$('blue-export').onclick=()=>{if(blueBusy||blueEditing)return;const index=$('character').value;window.parent.postMessage({type:'launcher-blue-report',role_id:index==='all'?(view==='calendar'?blueIds[calendarCharacter]:''):blueIds[Number(index)],date:view==='week'?weekStart:selectedDate,month:$('month').value,range:view==='week'?'week':view==='calendar'&&calendarMode==='period'?'period':'month',from:periodFrom,to:periodTo},window.parent.location.origin);};
