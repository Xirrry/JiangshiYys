<script setup>
import {computed,ref,watch} from 'vue';
import DojoIcon from './DojoIcon.vue';
import {compareResources,resourceClass,resourceTypes,resourceTypeOf} from './dojo/resource-presentation.js';
import {mailTypeLabel,mailSource} from './dojo/mail-source.js';
import './dojo/resource-style.css';
const props=defineProps({rows:{type:Array,default:()=>[]},describe:{type:Function,required:true},expandedByDefault:Boolean,showRole:{type:Boolean,default:true},paginate:Boolean,newestFirst:{type:Boolean,default:true}});
const expanded=ref({}),page=ref(1),size=10;
const key=row=>String(row.scope||'')+'|'+row.uid;
const cards=computed(()=>props.rows.slice().sort((a,b)=>props.newestFirst?b.time-a.time:a.time-b.time).map(row=>({...row,key:key(row),resources:row.items.map(([id,n])=>({id,n,...props.describe(id)})).sort(compareResources)})));
const pages=computed(()=>Math.max(1,Math.ceil(cards.value.length/size)));
const visible=computed(()=>props.paginate?cards.value.slice((page.value-1)*size,page.value*size):cards.value);
function isOpen(card){return expanded.value[card.key]??props.expandedByDefault}
const allOpen=computed(()=>visible.value.length>0&&visible.value.every(isOpen));
function toggle(card){expanded.value={...expanded.value,[card.key]:!isOpen(card)}}
function toggleAll(){const next=!allOpen.value;expanded.value={...expanded.value,...Object.fromEntries(visible.value.map(card=>[card.key,next]))}}
function groups(card){return resourceTypes.map(type=>({...type,items:card.resources.filter(item=>resourceTypeOf(item)===type.id)})).filter(type=>type.items.length)}
function timestamp(time){return new Date(time*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}
function itemText(item){return item.name+(item.stars?' '+item.stars+'星':'')+' × '+item.n.toLocaleString('zh-CN')}
watch(()=>props.rows.map(key).join(','),()=>{page.value=1;expanded.value={}});
</script>
<template><div class="reward-mail-list">
<div class="reward-mail-toolbar"><span>{{cards.length}} 封奖励邮件 <small>· 北京时间</small></span><button v-if="cards.length>1" @click="toggleAll">{{allOpen?'收起本页':'展开本页'}}</button></div>
<article v-for="card in visible" :key="card.key" class="reward-mail-card" :data-expanded="isOpen(card)">
<header class="reward-mail-heading"><div class="reward-mail-identity"><b v-if="showRole">{{card.label}}</b><time>{{timestamp(card.time)}}</time></div><span class="reward-mail-source" :class="mailSource(card)">{{mailTypeLabel(card)}}</span><button class="reward-mail-toggle" :aria-expanded="isOpen(card)" @click="toggle(card)">{{isOpen(card)?'收起资源':'全部资源 · '+card.resources.length}}<span aria-hidden="true">{{isOpen(card)?'⌃':'⌄'}}</span></button></header>
<div v-if="!isOpen(card)" class="reward-mail-preview"><span class="reward-mail-chip" :class="resourceClass(item.id)" v-for="item in card.resources.slice(0,6)" :key="item.id" :title="itemText(item)"><DojoIcon :id="item.id"/><span>{{item.name}}<i v-if="item.stars">{{item.stars}}星</i></span><b>{{item.n.toLocaleString('zh-CN')}}</b></span><button v-if="card.resources.length>6" class="reward-mail-more" @click="toggle(card)">另 {{card.resources.length-6}} 项 ›</button></div>
<div v-else class="reward-mail-groups"><section class="reward-mail-group" v-for="group in groups(card)" :key="group.id" :data-resource-type="group.id"><h4>{{group.label}}</h4><div><span class="reward-mail-chip" :class="resourceClass(item.id)" v-for="item in group.items" :key="item.id" :title="itemText(item)"><DojoIcon :id="item.id"/><span>{{item.name}}<i v-if="item.stars">{{item.stars}}星</i></span><b>{{item.n.toLocaleString('zh-CN')}}</b></span></div></section></div>
</article>
<nav class="reward-mail-pagination" v-if="paginate&&pages>1" aria-label="邮件分页"><span>共 {{cards.length}} 封 · 每页 {{size}} 封</span><button :disabled="page===1" @click="page--">上一页</button><span>{{page}} / {{pages}}</span><button :disabled="page===pages" @click="page++">下一页</button></nav>
</div></template>
<style scoped>
.reward-mail-list{color:#514a3f;font:13px/1.5 "Microsoft YaHei UI","Microsoft YaHei",sans-serif;min-width:0}
.reward-mail-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 10px;font-size:12px;color:#8b7b64}.reward-mail-toolbar small{font-size:11px;color:#a3937a}
.reward-mail-list button{font:inherit;cursor:pointer;border:1px solid #e1d5c1;border-radius:5px;background:#fcf9f2;color:#80694b;padding:5px 9px;white-space:nowrap}.reward-mail-list button:disabled{opacity:.4;cursor:default}
.reward-mail-card{border:1px solid #e6dccb;border-radius:9px;background:#fffdf7;margin-bottom:10px;padding:12px 15px;min-width:0}
.reward-mail-heading{display:flex;align-items:center;gap:12px;margin:0 0 9px;min-width:0}.reward-mail-identity{display:flex;gap:12px;align-items:baseline;min-width:0;flex-wrap:wrap}.reward-mail-identity b{font-size:14px;color:#4d5c50}.reward-mail-identity time{font-size:12px;color:#998970;white-space:nowrap;font-variant-numeric:tabular-nums}
.reward-mail-source{font-size:11px;line-height:1.6;padding:3px 8px;border-radius:4px;background:#eef2e9;color:#637755;white-space:nowrap}.reward-mail-source.xiajian{background:#eeeaf3;color:#86728e}
.reward-mail-toggle{margin-left:auto;display:flex;gap:9px;align-items:center;font-size:11px!important;border-color:transparent!important;background:transparent!important;color:#8a785c!important}
.reward-mail-preview{display:flex;flex-wrap:wrap;align-items:center;gap:6px}.reward-mail-chip{display:inline-flex;align-items:center;gap:5px;background:#f4efe4;border-radius:5px;padding:5px 8px;min-height:25px;box-sizing:border-box;font-size:12px;color:#73644d;white-space:nowrap;max-width:100%}
.reward-mail-chip :deep(.dojo-item-icon){width:25px;height:25px;margin:0 2px 0 0}.reward-mail-chip>span{white-space:normal;overflow-wrap:anywhere}.reward-mail-chip b{font-size:14px;margin-left:5px;font-weight:600;font-variant-numeric:tabular-nums}.reward-mail-chip i{font-size:11px;font-style:normal;color:#a47b38;margin-left:5px}
.reward-mail-more{font-size:11px!important;background:transparent!important;border-color:transparent!important;padding:6px!important}
.reward-mail-groups{border-top:1px solid #ede5d8;padding-top:5px}.reward-mail-group{display:grid;grid-template-columns:86px minmax(0,1fr);gap:10px;padding:7px 0;border-bottom:1px dashed #ede5d8;align-items:start}.reward-mail-group:last-child{border:0;padding-bottom:0}.reward-mail-group h4{font-size:11px;line-height:35px;font-weight:400;color:#a08c6e;margin:0}.reward-mail-group>div{display:flex;flex-wrap:wrap;gap:6px}
.reward-mail-pagination{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:8px 0;color:#927f63;font-size:12px}.reward-mail-pagination>span:first-child{margin-right:auto}
@media(max-width:850px){.reward-mail-card{padding:11px}.reward-mail-heading{gap:6px;flex-wrap:wrap}.reward-mail-identity{gap:5px 10px}.reward-mail-source{order:2}.reward-mail-group{grid-template-columns:1fr;gap:3px}.reward-mail-group h4{line-height:20px}.reward-mail-chip{font-size:11px;padding:4px 6px}.reward-mail-chip b{font-size:13px}}
:global(:root[data-skin="ink"]) .reward-mail-card{background:#282b29;border-color:#484b43}:global(:root[data-skin="ink"]) .reward-mail-chip{background:#34372f;color:#d4c7b4}:global(:root[data-skin="ink"]) .reward-mail-identity b{color:#d4d9c7}:global(:root[data-skin="ink"]) .reward-mail-source{background:#353e32;color:#b9c4a8}:global(:root[data-skin="ink"]) .reward-mail-source.xiajian{background:#3d3441;color:#cbb5d4}
</style>
