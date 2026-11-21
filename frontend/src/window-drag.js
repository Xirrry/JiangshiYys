// Physical-pixel rectangles shared by the two window canvases.
export function fits(r,work){return r[0]>=work[0]&&r[1]>=work[1]&&r[0]+r[2]<=work[0]+work[2]&&r[1]+r[3]<=work[1]+work[3]}
export function constrain(starts,delta,screens){
  const rs=Object.values(starts),valid=(dx,dy)=>rs.every(r=>screens.some(s=>fits([r[0]+dx,r[1]+dy,r[2],r[3]],s)));
  let [dx,dy]=delta.map(Math.round);if(valid(dx,dy))return [dx,dy];
  const xs=new Set([dx]),ys=new Set([dy]);
  for(const r of rs)for(const s of screens){xs.add(s[0]-r[0]);xs.add(s[0]+s[2]-r[0]-r[2]);ys.add(s[1]-r[1]);ys.add(s[1]+s[3]-r[1]-r[3])}
  let best=null,distance=Infinity;
  for(const x of xs)for(const y of ys){const d=(x-dx)**2+(y-dy)**2;if(d<distance&&valid(x,y)){best=[x,y];distance=d}}
  return best||[0,0];
}
export function snapMove(starts,delta,obstacles,screens,threshold=16,disabled=false){
  let [dx,dy]=constrain(starts,delta,screens);if(disabled)return [dx,dy];
  let sx=null,sy=null;
  const candidate=(axis,v)=>{if(Math.abs(v)>threshold)return;if(axis===0){if(sx===null||Math.abs(v)<Math.abs(sx))sx=v}else if(sy===null||Math.abs(v)<Math.abs(sy))sy=v};
  for(const r of Object.values(starts)){
    const a=[r[0]+dx,r[1]+dy,r[2],r[3]];
    for(const b of obstacles){
      if(a[1]<=b[1]+b[3]+threshold&&a[1]+a[3]>=b[1]-threshold)
        for(const e of [a[0],a[0]+a[2]])for(const target of [b[0],b[0]+b[2]])candidate(0,target-e);
      if(a[0]<=b[0]+b[2]+threshold&&a[0]+a[2]>=b[0]-threshold)
        for(const e of [a[1],a[1]+a[3]])for(const target of [b[1],b[1]+b[3]])candidate(1,target-e);
    }
    for(const b of screens){
      if(a[1]<=b[1]+b[3]&&a[1]+a[3]>=b[1]){candidate(0,b[0]-a[0]);candidate(0,b[0]+b[2]-a[0]-a[2])}
      if(a[0]<=b[0]+b[2]&&a[0]+a[2]>=b[0]){candidate(1,b[1]-a[1]);candidate(1,b[1]+b[3]-a[1]-a[3])}
    }
  }
  return constrain(starts,[dx+(sx??0),dy+(sy??0)],screens);
}
// One native request in flight, latest pending position replaces older ones.
export function liveMover(send,onResult=()=>{},onError=()=>{},delay=55){
  let pending=null,running=false,timer=null,waiters=[],stopped=false;
  const settle=()=>{if(!pending&&!running&&!timer)waiters.splice(0).forEach(resolve=>resolve())};
  async function pump(){timer=null;if(running)return;if(!pending){settle();return}
    const job=pending;pending=null;running=true;
    try{const result=await send(job);onResult(result,job)}catch(e){pending=null;stopped=true;onError(e,job)}
    finally{running=false;if(pending&&!stopped)timer=setTimeout(pump,delay);else settle()}
  }
  return {push(job){if(stopped)return;pending=job;if(!running&&!timer)timer=setTimeout(pump,delay)},
    reset(){stopped=false},
    flush(){if(timer){clearTimeout(timer);timer=null}if(!running&&pending)pump();return new Promise(resolve=>{waiters.push(resolve);settle()})},
    discard(){pending=null;if(timer){clearTimeout(timer);timer=null}settle()}};
}
