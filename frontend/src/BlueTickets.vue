<script setup>
import {ref,computed,onMounted,onUnmounted} from 'vue';
import BlueMail from './BlueMail.vue';
import BlueReportExport from './BlueReportExport.vue';
import workspace from './blue/workspace.html?raw';
import adapter from './blue/desktop-adapter.js?raw';
import compact from './blue/compact.css?raw';
import layout from './blue/desktop-layout.js?raw';
import ticket from './blue/blue-ticket-icon.png';
import fragment from './blue/black-fragment-icon.png';
import egg from './blue/black-egg-icon.png';
const emit=defineEmits(['dirty']);
const mailOpen=ref(false),mailRef=ref(null),syncBusy=ref(false),syncMessage=ref('');
async function syncMail(){if(syncBusy.value||frame.value?.contentWindow?.__blueCanLeave?.()===false)return;syncBusy.value=true;syncMessage.value='';try{const api=window.pywebview.api;const a=await api.blue_mail('archives');if(!a.ok)throw Error(a.error);const r=await api.blue_records('sync_mail',{revision:a.data.revision});if(!r.ok)throw Error(r.error);syncMessage.value=`已同步 ${r.data.synced} 个角色日记录`+(r.data.warnings.length?'；'+r.data.warnings.join('；'):'');frame.value?.contentWindow?.__blueReload?.();}catch(e){syncMessage.value=e.message}finally{syncBusy.value=false}}
const frame=ref(null),reportOpen=ref(false),reportInitial=ref({}),reportRef=ref(null);
const icons={'blue-ticket':ticket,'black-fragment':fragment,'black-egg':egg};
const html=computed(()=>workspace.replace('__DESKTOP_BLUE_STYLES__',()=>compact).replace('__BLUE_ICONS__',JSON.stringify(icons)).replace('__DESKTOP_BLUE_ADAPTER__',()=>adapter+'\n'+layout).replaceAll("url('black-egg-icon.png')",`url('${egg}')`).replaceAll('src="blue-ticket-icon.png"',`src="${ticket}"`));
function receive(e){if(e.source!==frame.value?.contentWindow||e.origin!==location.origin)return;if(e.data?.type==='launcher-blue-dirty')emit('dirty',!!e.data.dirty);if(e.data?.type==='launcher-blue-mail'){if(frame.value?.contentWindow?.__blueCanLeave?.()!==false)mailOpen.value=true;}if(e.data?.type==='launcher-blue-report'){reportInitial.value={role_id:e.data.role_id||'',date:e.data.date,month:e.data.month,range:e.data.range,from:e.data.from,to:e.data.to};reportOpen.value=true;}}
function canLeave(){if(mailOpen.value){if(mailRef.value?.canLeave()===false)return false;mailOpen.value=false;}if(reportOpen.value){if(reportRef.value?.canLeave()===false)return false;reportOpen.value=false;}return frame.value?.contentWindow?.__blueCanLeave?.()!==false;}
function dataExport(){if(reportRef.value?.canLeave()===false)return;reportOpen.value=false;frame.value?.contentWindow?.__blueOpenDataExport?.();}

defineExpose({canLeave});
onMounted(()=>window.addEventListener('message',receive));onUnmounted(()=>window.removeEventListener('message',receive));
</script>
<template><div class="blue-workspace"><div class="blue-sync-tools"><span>道馆邮件自动同步；手动修改保留。</span><button :disabled="syncBusy" @click="syncMail">{{syncBusy?'正在同步…':'同步已保存的道馆邮件'}}</button><span role="status" v-if="syncMessage">{{syncMessage}}</span></div><iframe ref="frame" title="蓝票记录" :srcdoc="html" class="blue-frame"></iframe><BlueMail v-if="mailOpen" ref="mailRef" @close="mailOpen=false" @updated="frame?.contentWindow?.__blueReload?.()" /><BlueReportExport v-if="reportOpen" ref="reportRef" :initial="reportInitial" @close="reportOpen=false" @data-export="dataExport" /></div></template>
<style scoped>.blue-sync-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 12px;color:#665b4a;background:#f6f2e8;font-size:13px}.blue-sync-tools button{border:1px solid #d8c9b4;background:#eee5d6;color:#604d39;border-radius:6px;padding:6px 10px;cursor:pointer}.blue-workspace{display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden;flex:1}.blue-frame{flex:1;min-height:0;width:100%;height:100%;border:0;display:block;background:#f6f2e8}</style>
