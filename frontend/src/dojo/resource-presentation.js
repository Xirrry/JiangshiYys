// Explicit resource-group rules override quantity/name modes; unrelated ties retain the saved order.
const pinned=[411,490001,434111];
const common=[490002,900007,900001,900090,900016,410];
export function savedResourceOrder(){try{const value=localStorage.getItem('dojo-item-sort');if(['common','name','quantity-desc','quantity-asc'].includes(value))return value}catch{}return 'common'}
function resourceStars(item){
 const id=Number(item.id);if(id>=-1006&&id<=-1001)return -1000-id;
 if([900197,900198,900199].includes(id))return id-900193;
 if(Number.isInteger(item.stars))return item.stars;
 const match=String(item.name||'').match(/([1-6一二三四五六])\s*星/);return match?Number(match[1])||'一二三四五六'.indexOf(match[1])+1:0;
}
function fixedGroupOrder(item){
 const id=Number(item.id),name=String(item.name||''),type=resourceTypeOf(item);
 if(type==='soul'){
  if([900217,900248].includes(id)||/大蛇的逆鳞/.test(name))return [0,0,0];
  if((id>=-1006&&id<=-1001)||/御魂/.test(name))return [0,1,-resourceStars(item)];
  if([900197,900198,900199].includes(id)||/青吉鬼/.test(name))return [0,2,-resourceStars(item)];
  return [0,3,0];
 }
 if(type==='growth'){
  if(/经验手札/.test(name)||(id>=1003118&&id<=1003123)){
   const levels={'极':6,'大':5,'中':4,'小':3,'微':2,'羸':1};
   const level=id>=1003118&&id<=1003123?id-1003117:levels[name.slice(-1)]||0;
   return [1,2,-level];
  }
  if([434111,434121,434131].includes(id)||/碎片|达摩碎/.test(name))return [1,1,0];
  return [1,0,0];
 }
 return [2,0,0];
}
export function compareResources(a,b,mode=savedResourceOrder()){
 const priority=id=>{const index=pinned.indexOf(Number(id));return index<0?pinned.length:index};
 const pin=priority(a.id)-priority(b.id);if(pin)return pin;
 const left=fixedGroupOrder(a),right=fixedGroupOrder(b);for(let i=0;i<left.length;i++){const delta=left[i]-right[i];if(delta)return delta}
 const nameOrder=()=>String(a.name||'').localeCompare(String(b.name||''),'zh-CN')||(a.stars||0)-(b.stars||0)||Number(a.id)-Number(b.id);
 if(mode==='quantity-desc')return b.n-a.n||nameOrder();
 if(mode==='quantity-asc')return a.n-b.n||nameOrder();
 if(mode==='name')return nameOrder();
 const rank=id=>{const index=common.indexOf(Number(id));return index<0?common.length:index};
 return rank(a.id)-rank(b.id)||nameOrder();
}
export function resourceClass(id){return Number(id)===411?'resource-daruma':Number(id)===434111?'resource-daruma-fragment':Number(id)===490001?'mystery-amulet':''}
export function resourceColor(id,fallback){return Number(id)===411?'#a67716':Number(id)===434111?'#99678d':Number(id)===490001?'#8050ac':fallback}
export function resourceHighlighted(id){return [411,490001,434111].includes(Number(id))}

export const resourceTypes=[{id:'soul',label:'御魂资源'},{id:'growth',label:'式神养成资源'},{id:'summon',label:'式神获取资源'},{id:'realm',label:'结界卡资源'},{id:'currency',label:'货币资源'},{id:'other',label:'其他资源'}];
export function resourceTypeOf(item){
 const id=Number(item.id),name=String(item.name||'');
 if(item.card||item.kind==='realm_card'||(id>=200000&&id<201000)||[960001,960004,960008].includes(id))return 'realm';
 if((id>=-1006&&id<=-1001)||[900197,900198,900199,900216,900217,900248].includes(id)||/御魂|青吉鬼|逆鳞|大蛇鳞片/.test(name))return 'soul';
 if([410,411,412,413,434111,434121,434131].includes(id)||/达摩|经验手札/.test(name))return 'growth';
 if([490001,490002,900007].includes(id)||/神秘的符咒|破碎的符咒|百鬼夜行门票/.test(name))return 'summon';
 if([900001,900090,900016].includes(id)||['金币','功勋','勋章'].includes(name))return 'currency';
 return 'other';
}
