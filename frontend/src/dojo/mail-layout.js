// Shared measured text layout: no detail icons and no hidden/truncated resources.
export function itemText(item){return item.name+(item.stars?' '+item.stars+'星':item.card?' 星级待识别':'')+' × '+item.n.toLocaleString('zh-CN');}
export function compactMailLayout(model,measure=s=>[...s].reduce((n,c)=>n+(c.charCodeAt(0)>255?16:9),0)){
 const maxWidth=822,gap=18,lineHeight=27;const groups=[];let cursor=238+Math.max(1,Math.ceil(model.totals.length/6))*124+66;
 for(const mail of model.mails){let group=groups.at(-1);if(!group||group.date!==mail.date){group={date:mail.date,mails:[]};groups.push(group)}
  const lines=[[]];let used=0;
  for(const item of mail.items){let token=itemText(item);const parts=[];
   if(measure(token)<=maxWidth-14)parts.push(token);else{let part='';for(const ch of token){if(part&&measure(part+ch)>maxWidth-14){parts.push(part);part=''}part+=ch}if(part)parts.push(part)}
   for(const text of parts){const width=measure(text)+14;if(used&&used+gap+width>maxWidth){lines.push([]);used=0}if(used)used+=gap;lines.at(-1).push({text,x:used,width});used+=width;}
  }
  if(!mail.items.length)lines[0].push({text:'奖励为空 / 未知',x:0,width:150});
  group.mails.push({...mail,lines,height:Math.max(48,lines.length*lineHeight+18)});
 }
 for(const group of groups){group.y=cursor;let y=cursor+42;group.mails=group.mails.map((mail,i)=>{const row={...mail,y,ordinal:i+1};y+=mail.height;return row});group.height=y-cursor+8;cursor+=group.height+14;}
 return {groups,height:cursor+85,summaryHeight:Math.max(1,Math.ceil(model.totals.length/6))*124};
}

export function iconMailLayout(model,measure=s=>String(s).length*11){const priority=id=>[490001,900001,490002,900007,900090].indexOf(id);const ordered=items=>items.slice().sort((a,b)=>{const x=priority(a.id),y=priority(b.id);return (x<0?99:x)-(y<0?99:y)||a.name.localeCompare(b.name,'zh-CN')||(a.stars||0)-(b.stars||0)});let cursor=238+Math.max(1,Math.ceil(model.totals.length/6))*124+66;const groups=[];for(const mail of model.mails){let group=groups.at(-1);if(!group||group.date!==mail.date){group={date:mail.date,mails:[]};groups.push(group)}const lines=[[]];let used=0;for(const item of ordered(mail.items)){const width=Math.max(87,48+measure(item.n.toLocaleString('zh-CN')));if(used&&used+width>822){lines.push([]);used=0}lines.at(-1).push({item,x:used,width});used+=width;}group.mails.push({...mail,lines,height:Math.max(58,lines.length*58+6)})}for(const group of groups){group.y=cursor;let y=cursor+42;group.mails=group.mails.map((mail,i)=>{const row={...mail,y,ordinal:i+1};y+=mail.height;return row});group.height=y-cursor+6;cursor+=group.height+14;}return {groups,height:cursor+85,summaryHeight:Math.max(1,Math.ceil(model.totals.length/6))*124};}
