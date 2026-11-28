<script setup>
import {useChecklistRoleDrag} from './checklist-role-drag.js';
import {isTaskComplete} from './checklist-status.js';
import {ref,computed} from 'vue';
import {groupChecklistRows} from './checklist-groups.js';
const props=defineProps({roles:{type:Array,default:()=>[]},busy:Boolean,groups:Array,groupAction:Function});
const emit=defineEmits(['open','read','group']);
const search=ref(''),pendingOnly=ref(false);
const complete=isTaskComplete;
function progress(r,period){const tasks=r.tasks.filter(t=>t.enabled&&t.available!==false&&t.priority!=='muted'&&!t.monitor&&!t.lifetime&&t.period===period);return {total:tasks.length,done:tasks.filter(complete).length,pending:tasks.filter(t=>!complete(t)&&t.status!=='unknown').length,unknown:tasks.filter(t=>t.status==='unknown').length}}
function timer(r,id){return r.tasks.find(t=>t.id===id&&t.enabled)}
function timedLabel(t){if(!t)return '未监控';if(t.status==='home')return '寄养回家了';if(t.status==='card_expired')return '已到期，待换卡';if(!t.ends_at)return '尚无有效记录';return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(t.ends_at*1000))+' 到期'}
function reminders(r){return r.tasks.filter(t=>t.enabled&&t.priority!=='muted'&&((t.storage?.remaining>0)||(['mentoring_recruit','lanqi_exchange'].includes(t.id)&&t.status==='ready'))).map(t=>({task:t,text:t.storage?.remaining>0?t.name+' · 上周储存剩余 '+t.storage.remaining+' 次（本周内有效）':t.id==='lanqi_exchange'?'兰契碎片可再次交换':'收徒冷却结束'}))}
const rows=computed(()=>props.roles.filter(r=>!search.value||(r.name+' '+r.server).includes(search.value.trim())).map(r=>({role:r,daily:progress(r,'daily'),weekly:progress(r,'weekly'),foster:timer(r,'d4'),card:timer(r,'realm_card'),reminders:reminders(r)})).filter(r=>!pendingOnly.value||r.daily.pending||r.daily.unknown||r.weekly.pending||r.weekly.unknown||r.foster?.status==='home'&&r.foster.priority!=='muted'||r.card?.status==='card_expired'&&r.card.priority!=='muted'||r.reminders.length));
const drag=useChecklistRoleDrag(payload=>props.groupAction?props.groupAction(payload):emit('group',payload));
function toggleGroup(group){const payload={action:'toggle',id:group.id,collapsed:!group.collapsed};if(props.groupAction)props.groupAction(payload);else emit('group',payload)}
async function moveGroupKey(event,id){
 if(!event.altKey||!['ArrowUp','ArrowDown'].includes(event.key))return;
 event.preventDefault();event.stopPropagation();
 if(drag.saving.value)return;
 const groups=props.groups||[],index=groups.findIndex(group=>group.id===id),down=event.key==='ArrowDown',target=groups[index+(down?1:-1)];
 if(index<0||!target)return;
 drag.saving.value=true;
 try{await (payload=>props.groupAction?props.groupAction(payload):emit('group',payload))({action:'group_move',id,before:target.id,after:down})}
 finally{drag.saving.value=false}
}
const groupedRows=computed(()=>groupChecklistRows(props.groups,rows.value,r=>r.role,true));
const updated=r=>r.read_at?.slice(5,16).replace('T',' ')||'暂无读取时间';
function freshnessSummary(r){const tasks=r.tasks.filter(t=>t.enabled&&t.available!==false);if(r.read_error)return '读取失败，保留原记录';const fresh=tasks.filter(t=>t.freshness==='fresh').length,old=tasks.filter(t=>['retained','failed'].includes(t.freshness)).length;return [fresh?'已更新 '+fresh+' 项':'',old?'沿用旧记录 '+old+' 项':''].filter(Boolean).join(' · ')||'尚无本次更新信息'};
</script>
<template>
<section class="overview">
 <div class="overview-tools"><div><h2>全部角色 <span>{{roles.length}}</span></h2><p>每日、每周进度与到期提醒</p></div><div class="overview-filters"><input aria-label="搜索总览角色" v-model="search" placeholder="搜索角色 / 区服"><label><input type="checkbox" v-model="pendingOnly"> 只看待处理</label></div></div>
 <p v-if="drag.error.value" class="drag-error" role="status">{{drag.error.value}}</p>
 <div class="overview-table" :aria-busy="drag.saving.value"><table><thead><tr><th>角色</th><th>每日任务</th><th>每周任务</th><th>好友寄养</th><th>自己的结界卡</th><th>其他提醒</th><th></th></tr></thead><tbody @click.capture="drag.click($event)">
 <template v-for="g in groupedRows" :key="g.id"><tr v-if="g.showHeader" class="overview-group" :data-checklist-group="g.id" draggable="true" @dragstart="drag.startGroup($event,g.id)" @dragend="drag.clear" title="拖动分组标题调整顺序，或按 Alt + ↑ / ↓ 移动分组" :class="{'drag-group-target':drag.hoverGroup.value===g.id,'role-dragging':drag.groupDragged.value===g.id,'role-drop-before':drag.groupHovered.value===g.id&&!drag.groupAfter.value,'role-drop-after':drag.groupHovered.value===g.id&&drag.groupAfter.value}" @dragover="drag.overGroup($event,g.id)" @drop="drag.drop($event,g.id)"><td colspan="7"><button :aria-expanded="!!search||!g.collapsed" @keydown="moveGroupKey($event,g.id)" @click="toggleGroup(g)"><span>{{search||!g.collapsed?'▾':'▸'}} {{g.name}}</span><small>{{g.rows.length}} 位角色</small></button></td></tr>
 <tr v-for="r in (search||!g.collapsed?g.rows:[])" :key="r.role.key" :data-role-key="r.role.key" draggable="true" :class="{'role-dragging':drag.dragged.value===r.role.key,'role-drop-before':drag.hovered.value===r.role.key&&!drag.after.value,'role-drop-after':drag.hovered.value===r.role.key&&drag.after.value}" @dragstart="drag.start($event,r.role.key)" @dragend="drag.clear" @dragover="drag.overRole($event,r.role.key)" @drop="drag.drop($event,g.id,r.role.key)" title="拖动排序，拖到分组标题可移动分组">
 <td><button class="role-link" @click="emit('open',r.role.key,'daily')">{{r.role.name}}</button><small>{{r.role.server||'区服待识别'}}</small><small class="updated">最近尝试 {{updated(r.role)}}</small><small class="updated" :title="r.role.read_error">{{freshnessSummary(r.role)}}</small></td>
 <td v-for="p in ['daily','weekly']" :key="p"><button class="progress-link" @click="emit('open',r.role.key,p)"><template v-if="r[p].total"><strong :class="{finished:r[p].done===r[p].total}">{{r[p].pending?'剩 '+r[p].pending+' 项':r[p].unknown?'待核对':'已完成'}}</strong><span class="mini-track"><i :style="{width:r[p].done/r[p].total*100+'%'}"></i></span><small>{{r[p].done}} / {{r[p].total}} 已完成<span v-if="r[p].unknown"> · {{r[p].unknown}} 项未知</span></small></template><small v-else>暂无提醒任务</small></button></td>
 <td v-for="(t,index) in [r.foster,r.card]" :key="index"><span :class="{due:t?.priority!=='muted'&&['home','card_expired'].includes(t?.status)}" :title="t?.detail">{{timedLabel(t)}}</span><small v-if="t?.status==='fostering'">{{t.target_name||'好友结界'}}</small><small v-if="t?.status==='card_running'">{{t.card_name||'结界卡生效中'}}</small></td>
 <td><span v-for="n in r.reminders" :key="n.task.id" class="due reminder" :title="n.task.detail">{{n.text}}</span><span v-if="!r.reminders.length" class="muted">—</span></td>
 <td class="row-actions"><button :disabled="busy" @click="emit('read',r.role.key)">读取</button><button @click="emit('open',r.role.key,'daily')">明细 ›</button></td>
 </tr></template></tbody></table><p v-if="!rows.length" class="empty">{{roles.length?'没有符合筛选的角色':'检测运行窗口后，角色记录会显示在这里。'}}</p></div>
 <p class="overview-note">未知项单独列出；不提醒任务与累计福利不计入待办进度，每日礼包领取后才算完成；其他待领取奖励不催领。到期时间为北京时间，读取失败保留上次记录。</p>
</section>
</template>
<style scoped>
.overview{color:#3b413b}.overview-tools{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 0 20px;flex-wrap:wrap}h2{font-size:18px;margin:0 0 6px;font-weight:600}h2 span{font-size:12px;color:#998a74;font-weight:400;margin-left:8px}p{font-size:12px;color:#998a74;margin:0}.overview-filters{display:flex;align-items:center;gap:18px;flex-wrap:wrap}input:not([type=checkbox]){width:210px;padding:9px 12px;border:1px solid #dfd3bf;border-radius:6px;background:#fffcf6;color:inherit}label{font-size:12px;white-space:nowrap}input{accent-color:#456052}.overview-table{border:1px solid #e4dac9;border-radius:9px;background:#fffcf6;overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:12px}th{background:#f1ecdf;font-size:11px;color:#97856d;font-weight:400;padding:13px 16px;white-space:nowrap}td{color:#7d7566;padding:16px;vertical-align:middle;border-top:1px solid #eee7da;line-height:1.7}tbody tr:hover{background:#f8f5ec}td:first-child{min-width:115px}small{display:block;font-size:11px;color:#998d79;font-weight:400}.updated{font-size:10px;color:#b0a48f;margin-top:4px}button{font:inherit;cursor:pointer;color:inherit}button:disabled{opacity:.45;cursor:wait}.role-link,.progress-link{border:0;padding:0;background:transparent;text-align:left}.role-link{font-size:14px;font-weight:600}.role-link:hover{text-decoration:underline;text-underline-offset:3px}.progress-link{min-width:115px;width:100%}.progress-link strong{font-size:13px;font-weight:500;color:#9f7848}.progress-link strong.finished{color:#708665}.mini-track{display:block;width:85px;height:3px;background:#e8e4d8;border-radius:3px;margin:8px 0}.mini-track i{display:block;height:100%;background:#8ca080;border-radius:3px}.due{color:#ac7939}.reminder{display:block;font-size:11px}.muted{color:#b2a58f}.row-actions{white-space:nowrap}.row-actions button{border:0;background:transparent;padding:5px 6px;color:#6f7f6b;font-size:11px}.row-actions button:hover{background:#e9eddf;border-radius:4px}.overview-note{font-size:11px;margin-top:15px;line-height:1.8}.empty{padding:45px 20px;text-align:center}@media(max-width:1150px){td,th{padding:12px 10px}.row-actions button{display:block}.progress-link{min-width:95px}}
.overview-group td{padding:0;background:#f3eee3}.overview-group button{display:flex;align-items:center;gap:12px;width:100%;text-align:left;border:0;padding:11px 16px;background:transparent;color:#897c69;font-size:12px}.overview-group small{font-size:10px;color:#ab9d86}
.overview{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden}.overview-tools,.overview-note{flex:none}.overview-table{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}.overview-table thead th{position:sticky;top:0;z-index:2}.overview-note{margin-top:10px}
.overview-group[draggable=true],.overview-group[draggable=true] button{cursor:grab}.drag-error{color:#a45038;margin-bottom:8px}.role-dragging{opacity:.4}.role-drop-before{box-shadow:inset 0 2px #6d8668!important}.role-drop-after{box-shadow:inset 0 -2px #6d8668!important}.drag-group-target{background:#dce6d4!important;outline:1px dashed #829776}.role-scroll [draggable=true]{cursor:grab}.role-scroll [draggable=true]:active{cursor:grabbing}
</style>
