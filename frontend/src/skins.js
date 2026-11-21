import {ref} from 'vue';
import './skins.css';
export const skins = [
  {id:'paper',name:'暖纸',description:'米色纸面 · 温暖沉静',colors:['#f6f2ea','#eee4d2','#785b40']},
  {id:'bamboo',name:'竹青',description:'灰绿底色 · 清爽自然',colors:['#f0f1ec','#e6e9e1','#627460']},
  {id:'mist',name:'雾蓝',description:'冷灰蓝调 · 轻盈简洁',colors:['#f0f1f2','#e7e9eb','#687b8a']},
  {id:'ink',name:'墨夜',description:'深色石墨 · 柔和低亮',colors:['#222527','#303436','#586d68']},
];
export const activeSkin = ref('paper');
export function chooseSkin(id) {
  if (!skins.some(s => s.id === id)) return;
  activeSkin.value = id;
  document.documentElement.dataset.skin = id;
  try {localStorage.setItem('launcher-skin',id);} catch {}
}
let saved='paper';
try {saved=localStorage.getItem('launcher-skin')||'paper';} catch {}
chooseSkin(saved);
