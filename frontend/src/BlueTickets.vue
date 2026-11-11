<script setup>
import {ref,computed,onMounted,onUnmounted} from 'vue';
import BlueReportExport from './BlueReportExport.vue';
import workspace from './blue/workspace.html?raw';
import adapter from './blue/desktop-adapter.js?raw';
import compact from './blue/compact.css?raw';
import layout from './blue/desktop-layout.js?raw';
import ticket from './blue/blue-ticket-icon.png';
import fragment from './blue/black-fragment-icon.png';
import egg from './blue/black-egg-icon.png';
const emit=defineEmits(['dirty']);
const frame=ref(null),reportOpen=ref(false),reportInitial=ref({}),reportRef=ref(null);
const icons={'blue-ticket':ticket,'black-fragment':fragment,'black-egg':egg};
const html=computed(()=>workspace.replace('__DESKTOP_BLUE_STYLES__',()=>compact).replace('__BLUE_ICONS__',JSON.stringify(icons)).replace('__DESKTOP_BLUE_ADAPTER__',()=>adapter+'\n'+layout).replaceAll("url('black-egg-icon.png')",`url('${egg}')`).replaceAll('src="blue-ticket-icon.png"',`src="${ticket}"`));
function receive(e){if(e.source!==frame.value?.contentWindow||e.origin!==location.origin)return;if(e.data?.type==='launcher-blue-dirty')emit('dirty',!!e.data.dirty);if(e.data?.type==='launcher-blue-report'){reportInitial.value={role_id:e.data.role_id||'',date:e.data.date,month:e.data.month,range:e.data.range,from:e.data.from,to:e.data.to};reportOpen.value=true;}}
function canLeave(){if(reportOpen.value){if(reportRef.value?.canLeave()===false)return false;reportOpen.value=false;}return frame.value?.contentWindow?.__blueCanLeave?.()!==false;}
function dataExport(){if(reportRef.value?.canLeave()===false)return;reportOpen.value=false;frame.value?.contentWindow?.__blueOpenDataExport?.();}

defineExpose({canLeave});
onMounted(()=>window.addEventListener('message',receive));onUnmounted(()=>window.removeEventListener('message',receive));
</script>
<template><div class="blue-workspace"><iframe ref="frame" title="蓝票记录" :srcdoc="html" class="blue-frame"></iframe><BlueReportExport v-if="reportOpen" ref="reportRef" :initial="reportInitial" @close="reportOpen=false" @data-export="dataExport" /></div></template>
<style scoped>.blue-workspace{height:100%;min-height:0;overflow:hidden;flex:1}.blue-frame{width:100%;height:100%;border:0;display:block;background:#f6f2e8}</style>
