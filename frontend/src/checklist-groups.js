export function groupChecklistRows(groups,rows,roleOf=r=>r){
 const list=groups?.length?groups:[{id:'',name:'未分组',collapsed:false}];
 const ids=new Set(list.map(g=>g.id));
 return list.map(group=>({...group,rows:rows.filter(row=>{const id=roleOf(row).group_id||'';return (ids.has(id)?id:'')===group.id})})).filter(g=>g.rows.length);
}
