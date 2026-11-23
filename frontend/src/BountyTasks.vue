<script setup>
import {ref,onMounted,onUnmounted} from 'vue';
import workspaceCss from './workspace-layout.css?raw';
import page from './bounty-page.html?raw';
import {rewardIcons} from './bounty-icons.js';
const props=defineProps({launchRole:Function,roleLabel:Function,roles:{type:Array,default:()=>[]}});
const frame=ref(null);
async function launcherMessage(event){
 if(event.source!==frame.value?.contentWindow||event.data?.channel!=='bounty-launch')return;
 const {id,action,keys,key}=event.data;
 try{
  if(!['matches','launch'].includes(action))throw Error('操作无效');
  const response=await window.pywebview.api.bounty_tasks('launch_matches',{keys:action==='launch'?[key]:keys});
  if(!response.ok)throw Error(response.error);
  if(action==='launch'){
   const role=props.roles.find(r=>r.id===response.data[key]);
   if(!role)throw Error('角色管理中已无匹配角色，请刷新记录');
   await props.launchRole(role.id);
  }
  const matches={};for(const [key,id] of Object.entries(response.data)){
   const role=props.roles.find(r=>r.id===id);if(role)matches[key]={label:props.roleLabel(role)};
  }
  event.source.postMessage({channel:'bounty-launch-reply',id,ok:true,data:matches},'*');
 }catch(error){event.source.postMessage({channel:'bounty-launch-reply',id,ok:false,error:error.message},'*')}
}
onMounted(()=>window.addEventListener('message',launcherMessage));
onUnmounted(()=>window.removeEventListener('message',launcherMessage));
const bridge = `<script>
let launcherSequence=0;const launcherPending=new Map();
function launcherRequest(action,payload){return new Promise((resolve,reject)=>{const id=++launcherSequence;launcherPending.set(id,{resolve,reject});parent.postMessage({channel:'bounty-launch',id,action,...payload},'*')})}
addEventListener('message',event=>{if(event.source!==parent||event.data?.channel!=='bounty-launch-reply')return;const item=launcherPending.get(event.data.id);if(!item)return;launcherPending.delete(event.data.id);event.data.ok?item.resolve(event.data.data):item.reject(Error(event.data.error))});
window.bountyRewardIcons = ${JSON.stringify(rewardIcons)};
window.pywebview = {api: {
 launch_matches: keys => launcherRequest('matches',{keys}),
 launch_role: key => launcherRequest('launch',{key}),
 windows: () => parent.pywebview.api.bounty_tasks('windows'),
 history: day => parent.pywebview.api.bounty_tasks('history', {day}),
 read: target => parent.pywebview.api.bounty_tasks('read', {target})
}};
<\/script>`;
const content = page.replace('</style>','</style><style>'+workspaceCss+'</style>').replace('<script>', bridge + '<script>');
</script>
<template><iframe ref="frame" class="bounty-page" title="每日悬赏" :srcdoc="content"></iframe></template>
<style scoped>
.bounty-page { width:100%; height:100%; min-height:0; border:0; display:block; }
</style>
