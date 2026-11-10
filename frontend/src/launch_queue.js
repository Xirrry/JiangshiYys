// Queue submission and observed readiness are separate; stopping never closes submitted games.
export function abortableDelay(ms, signal) {
  if (signal.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    const finish = value => { clearTimeout(timer); signal.removeEventListener('abort', cancel); resolve(value); };
    const cancel = () => finish(false);
    const timer = setTimeout(() => finish(true), ms);
    signal.addEventListener('abort', cancel, {once:true});
  });
}
const pending = new Set(['queued','starting','submitted']);
export function createLaunchQueue({preflight, dispatch, onChange=()=>{}, sleep=abortableDelay, now=()=>Date.now(), token}={}) {
  let sequence=0, controller=null, context=null;
  let state={items:[],dispatching:false,message:'',stopped:false};
  const copy=x=>JSON.parse(JSON.stringify(x));
  const publish=()=>onChange(copy(state));
  const newToken=token||(()=>`queue-${now()}-${++sequence}`);
  const busy=()=>state.dispatching||state.items.some(x=>pending.has(x.status));
  async function run(ids, nextContext, retry=false) {
    if(busy()) throw Error('请等待当前队列结束，或先停止后续启动');
    if(!ids.length) return;
    if(new Set(ids).size!==ids.length) throw Error('启动角色不能重复');
    if(!Number.isFinite(nextContext.delay)||nextContext.delay<0||nextContext.delay>300) throw Error('启动间隔需为 0～300 秒');
    context=copy(nextContext);controller=new AbortController();const signal=controller.signal;
    const selected=new Set(ids);
    if(retry) {
      state.items=state.items.map(x=>selected.has(x.id)?{id:x.id,label:x.label,token:newToken(),status:'queued',error:''}:x);
    } else state.items=ids.map(id=>({id,label:context.names?.[id]||id,token:newToken(),status:'queued',error:''}));
    state.name=context.name||'当前组合';state.dispatching=true;state.stopped=false;state.message='正在检查启动条件';publish();
    try {
      await preflight(ids,copy(context));
      for(let i=0;i<ids.length;i++) {
        if(signal.aborted) break;
        const row=state.items.find(x=>x.id===ids[i]);
        if(i>0&&context.delay>0) {
          state.message=`等待 ${context.delay} 秒 · ${i}/${ids.length}`;publish();
          if(!await sleep(context.delay*1000,signal)) break;
        }
        if(signal.aborted) break;
        row.status='starting';state.message=`提交 ${i+1}/${ids.length}`;publish();
        try {
          const result=await dispatch(row.id,row.token,copy(context));
          if(result?.error) {row.status='failed';row.error=result.error;}
          else if(result?.needs_rebind) {row.status='rebind';row.error='请先完成角色登录绑定';}
          else if(result?.focused) row.status='ready';
          else {row.status='submitted';row.submittedAt=now();}
        } catch(error) {row.status='failed';row.error=error.message||'启动请求失败';}
        publish();
      }
    } catch(error) {
      for(const row of state.items) if(selected.has(row.id)&&row.status==='queued') {
        row.status='failed';row.error=error.message||'启动检查失败';
      }
      state.message=error.message||'启动检查失败';
    } finally {
      if(signal.aborted) for(const row of state.items) if(row.status==='queued') row.status='cancelled';
      state.dispatching=false;
      if(signal.aborted) state.message='已停止后续启动';
      else if(state.items.some(x=>x.status==='submitted')) state.message='正在等待游戏窗口就绪';
      publish();
    }
  }
  return {
    run,
    retry() {return run(state.items.filter(x=>x.status==='failed').map(x=>x.id),context,true);},
    stop() {
      controller?.abort();state.stopped=true;state.message='已停止后续启动';
      for(const row of state.items) if(row.status==='queued') row.status='cancelled';
      publish();
    },
    reconcile(launches={},routes={}) {
      let changed=false;
      for(const row of state.items) if(row.status==='submitted') {
        const launch=launches[row.id];
        if(launch?.request_id===row.token) {
          if(launch.phase==='ready') {row.status='ready';row.error='';changed=true;}
          else if(launch.phase==='failed') {row.status='failed';row.error=launch.error||'启动失败';changed=true;}
          else if(launch.phase==='cancelled') {row.status='cancelled';changed=true;}
        }
        if(row.status==='submitted'&&now()-row.submittedAt>180000) {
          row.status='failed';row.error='等待窗口就绪超时，请查看游戏及代理状态后重试';changed=true;
        }
      }
      if(changed) publish();
    },
    clear() {if(busy()) return false;state={items:[],dispatching:false,message:'',stopped:false};publish();return true;},
    snapshot:()=>copy(state),
    busy
  };
}
