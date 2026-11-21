<script setup>
import page from './bounty-page.html?raw';
import {rewardIcons} from './bounty-icons.js';
const bridge = `<script>
window.bountyRewardIcons = ${JSON.stringify(rewardIcons)};
window.pywebview = {api: {
 windows: () => parent.pywebview.api.bounty_tasks('windows'),
 history: day => parent.pywebview.api.bounty_tasks('history', {day}),
 read: target => parent.pywebview.api.bounty_tasks('read', {target})
}};
<\/script>`;
const content = page.replace('<script>', bridge + '<script>');
</script>
<template><iframe class="bounty-page" title="每日悬赏" :srcdoc="content"></iframe></template>
<style scoped>
.bounty-page { width:100%; height:100%; min-height:0; border:0; display:block; }
</style>
