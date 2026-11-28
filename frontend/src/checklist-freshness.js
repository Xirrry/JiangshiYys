export function freshnessLabel(task){
 if(task.available===false)return task.id==='d9'?'周六开放':'今日未开放';
 return {fresh:'本次已更新',retained:'沿用旧记录',failed:'读取失败 · 沿用旧记录',manual:'手动确认',missing:'未读到数据',unsupported:'暂未接入'}[task.freshness]||(task.source==='manual'?'手动确认':task.at?'上次记录':'未读到数据');
}
export function freshnessTip(task){
 return [freshnessLabel(task),task.at?'数据更新于 '+task.at.slice(0,19).replace('T',' '):'',task.read_at?'最近尝试于 '+task.read_at.slice(0,19).replace('T',' '):'',task.freshness==='missing'?'可能需要先打开或刷新游戏对应界面；不据此判断未完成':''].filter(Boolean).join(' · ');
}
