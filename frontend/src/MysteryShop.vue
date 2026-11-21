<script setup>
import page from './mystery-shop-page.html?raw';
const bridge = `<script>
async function shopCall(action,payload={}) {
 const result=await parent.pywebview.api.mystery_shop(action,payload);
 if(!result.ok)throw new Error(result.error||'神秘商店操作失败');
 return result.data;
}
window.pywebview={api:{load:()=>shopCall('load'),windows:()=>shopCall('windows'),read:target=>shopCall('read',{target})}};
<\/script>`;
const content=page.replace('<script>',bridge+'<script>');
</script>
<template><iframe class="shop-page" title="神秘商店" :srcdoc="content"></iframe></template>
<style scoped>
.shop-page{width:100%;height:100%;min-height:0;border:0;display:block;}
</style>
