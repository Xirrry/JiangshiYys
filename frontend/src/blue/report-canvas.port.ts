import ticketArt from './blue-ticket-icon.png';
import fragmentArt from './black-fragment-icon.png';
import eggArt from './black-egg-icon.png';
import knotArt from './enmusubi-hanging-ornament.png';
const ART=[ticketArt,fragmentArt,eggArt,knotArt];
import {attemptText,type BlueReport} from './report-model.js';
import {blueComplete,blueKnown,bluePending,blueTotal} from './report-model.js';
const W=1080,SCALE=2,M=46,GAP=10,CARD_H=160,GRID_Y=397;
const ink='#493c34',muted='#927d68',rose='#b64634',line='#e6d9c6';
let icons:Promise<Array<HTMLImageElement|null>>|undefined;
function loadIcons(){return icons??=Promise.all(ART.map(url=>new Promise<HTMLImageElement|null>(resolve=>{const img=new Image(),timer=setTimeout(()=>resolve(null),4000);img.onload=()=>{clearTimeout(timer);resolve(img);};img.onerror=()=>{clearTimeout(timer);resolve(null);};img.src=url;})));}
export function reportCardLayout(model:BlueReport,page:number){
 const rows=model.rows.slice((page-1)*31,page*31),offset=(new Date(rows[0].date+'T00:00:00Z').getUTCDay()+6)%7;
 return {cards:rows.map((row,i)=>({...row,column:(offset+i)%7,week:Math.floor((offset+i)/7)})),weeks:Math.ceil((offset+rows.length)/7)};
}
export async function renderReport(model:BlueReport,kind:string,page:number,loadedAt:string){
 const art=await loadIcons(),pages=Math.ceil(model.days/31),{cards,weeks}=reportCardLayout(model,page),gridEnd=GRID_Y+weeks*(CARD_H+GAP)-GAP,H=gridEnd+139;
 const hasXiajian=model.rows.some(row=>row.record?.mode==='xiajian');
 const canvas=document.createElement('canvas');canvas.width=W*SCALE;canvas.height=H*SCALE;const context=canvas.getContext('2d');if(!context)throw Error('当前浏览器无法生成图片。');const ctx=context;ctx.scale(SCALE,SCALE);
 ctx.fillStyle='#fffdf7';ctx.fillRect(0,0,W,H);const wash=ctx.createRadialGradient(W,0,0,W,0,550);wash.addColorStop(0,'#f4e5cc70');wash.addColorStop(1,'#fffdf700');ctx.fillStyle=wash;ctx.fillRect(0,0,W,H);
 function text(value:unknown,x:number,y:number,size=18,color=ink,bold=false,max=W-M*2,font='"Microsoft YaHei","PingFang SC",sans-serif'){
  ctx.fillStyle=color;ctx.font=`${bold?'600':'400'} ${size}px ${font}`;let s=String(value);while(ctx.measureText(s).width>max&&s.length>1)s=s.slice(0,-2)+'…';ctx.fillText(s,x,y);
 }
 function rule(y:number){ctx.strokeStyle=line;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(M,y);ctx.lineTo(W-M,y);ctx.stroke();}
 function rounded(x:number,y:number,w:number,h:number,fill:string,stroke?:string){ctx.beginPath();ctx.roundRect(x,y,w,h,9);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();}}
 function icon(index:number,x:number,y:number,size:number){if(art[index])ctx.drawImage(art[index]!,x,y,size,size);else text(['票','碎','蛋'][index],x,y+size*.78,size*.65,muted);}
 // Hanging red cord and compact knot; shared with the page background artwork.
 if(art[3]){
  const layer=document.createElement('canvas');layer.width=640;layer.height=440;const d=layer.getContext('2d');
  if(d){d.scale(2,2);d.drawImage(art[3]!, -380,-8,700,467);d.globalCompositeOperation='destination-in';const left=d.createLinearGradient(0,0,65,0);left.addColorStop(0,'#0000');left.addColorStop(1,'#000');d.fillStyle=left;d.fillRect(0,0,320,220);const bottom=d.createLinearGradient(0,150,0,220);bottom.addColorStop(0,'#000');bottom.addColorStop(1,'#0000');d.fillStyle=bottom;d.fillRect(0,0,320,220);ctx.save();ctx.globalAlpha=.52;ctx.drawImage(layer,760,0,320,220);ctx.restore();}
 }

 text(hasXiajian?'道馆 · 狭间':'道馆',M,47,13,muted,false,250);const title=kind==='周度'?'一周掉落手记':kind==='月度'?'本月掉落手记':'自选日期掉落手记';text(title,M,91,31,ink,true,750);
 text(`${model.from.replaceAll('-','.')} — ${model.to.replaceAll('-','.')}`,M,124,17,muted);
 text(model.identity.label,M,169,23,ink,true,720);const subject=model.identity.server;text(subject,M,199,16,muted,false,720);
 rule(220);icon(0,M+2,247,32);text('已知蓝票产出',M+51,247,14,muted);text(`${model.total??'—'} 张`,M+51,281,28,rose,false,390);
 text(`道馆 ${model.dojo??'—'} 张`,M+51,307,13,muted,false,180);
 if(hasXiajian){text(`狭间 ${model.xiajian??'—'} 张`,M+229,307,13,muted,false,180);
 for(const [index,x,label,value,unit] of [[1,570,'黑碎',model.fragments,'片'],[2,824,'黑蛋',model.eggs,'个']] as const){icon(index,x,257,31);text(label,x+45,251,14,muted);text(`${value??'—'} ${unit}`,x+45,284,25,ink,false,150);}}
 rule(329);text(kind==='周度'?'七日掉落':'每日掉落',M,363,18,ink,true);if(pages>1)text(`第 ${page} / ${pages} 张 · 汇总为全区间`,W-340,363,13,muted,false,295);
 const cw=(W-M*2-GAP*6)/7,weekdays=['周一','周二','周三','周四','周五','周六','周日'];weekdays.forEach((d,i)=>text(d,M+i*(cw+GAP)+12,385,12,i>4?'#b18b67':muted));
 for(const item of cards){const x=M+item.column*(cw+GAP),y=GRID_Y+item.week*(CARD_H+GAP),r=item.record,partial=!!r&&bluePending(r),known=!!r&&blueKnown(r),total=r?blueTotal(r):0,complete=!!r&&blueComplete(r),luck=!!r&&r.mode==='daily'&&complete&&known&&model.luckAverage!==null&&model.luckAverage>0?(total>model.luckAverage*2?'欧':total<model.luckAverage/2?'非':'平'):'',gold=!!r&&r.mode==='xiajian'&&(r.eggs??0)>0;
  ctx.save();if(partial)ctx.setLineDash([4,4]);rounded(x,y,cw,CARD_H,'#fffefd',gold?'#d9be83':line);ctx.restore();
  if(gold||r?.mode==='daily'){ctx.save();ctx.beginPath();ctx.roundRect(x+1,y+1,cw-2,CARD_H-2,8);ctx.clip();const g=ctx.createLinearGradient(x,y,x+cw,y+CARD_H);const shade=(n:number|null)=>n===null?'#fffdf9':n===0?'#e9eae6':n<=2?'#e0efdc':n<=4?'#dceafb':n<=6?'#eadcf7':n<=9?'#f9e6b1':'#f6d1d0';const [low,high]=[r!.first,r!.second].sort((a,b)=>(a??-1)-(b??-1));g.addColorStop(0,gold?'#fffdf7':shade(low));g.addColorStop(1,gold?'#f8e8c780':shade(high));ctx.fillStyle=g;ctx.fillRect(x,y,cw,CARD_H);ctx.restore();}
  text(item.date.slice(5).replace('-','.'),x+12,y+25,14,ink,false,cw-24);ctx.strokeStyle='#f0e7e7';ctx.beginPath();ctx.moveTo(x+10,y+36);ctx.lineTo(x+cw-10,y+36);ctx.stroke();
  if(!r){text(({future:'未到日期',missing:'未记录'} as Record<string,string>)[item.state]??'未记录',x+12,y+84,14,muted,false,cw-24);text('—',x+12,y+116,18,muted);continue;}
  if(luck){ctx.save();ctx.globalAlpha=gold?0.07:luck==='欧'?0.11:0.05;ctx.translate(x+cw-36,y+CARD_H-13);ctx.rotate(-.13);text(luck,-22,0,57,luck==='欧'?'#b58d3f':'#95778b',false,90,'KaiTi,"楷体",serif');ctx.restore();}
  text(r.mode==='daily'?'道馆':'狭间',x+12,y+62,12,muted,false,cw-24);icon(0,x+12,y+77,18);text(known?total:'—',x+39,y+94,20,ink,false,cw-49);
  if(r.mode==='daily'){
   for(const [field,label,dy] of [['first','第1次',116],['second','第2次',136]] as const){
    const value=attemptText(r,field);text(label,x+12,y+dy,10,muted,false,40);
    text(/^\d+$/.test(value)?`${value} 张`:value,x+59,y+dy,12,ink,false,cw-71);
   }
  }
  else{icon(1,x+11,y+108,17);text(r.fragments??'—',x+31,y+122,13,muted,false,28);icon(2,x+cw/2+1,y+108,17);text(r.eggs??'—',x+cw/2+22,y+122,13,gold?'#a47c37':muted,false,35);}
  if(partial||!known)text(partial?'待补 · 仅计已知':'仅计已知产出',x+11,y+153,9,'#b08b52',false,cw-22);
 }
 text(`已记录 ${model.recorded} 天 · 完整数值 ${model.complete} 天`,M,gridEnd+32,13,muted,false,450);
 const quality=[model.pending?`待补 ${model.pending} 天`:'',model.unknown?`未知 ${model.unknown} 次`:'',model.missed?`未打 ${model.missed} 次`:'',model.missing?`未记录 ${model.missing} 天`:''].filter(Boolean).join(' · ');text(quality,M,gridEnd+57,12,muted);
 rule(gridEnd+75);text('仅计已知产出；未知、未打、未记录不当作零。',M,gridEnd+100,12,muted,false,620);text(`数据：${new Date(loadedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}`,W-346,gridEnd+100,10,muted,false,300);
 return new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('生成PNG失败，请重试。')),'image/png'));
}
