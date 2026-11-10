import assert from 'node:assert/strict';
import {createLaunchQueue,abortableDelay} from './launch_queue.js';
const ctx={delay:0,layoutIds:['a','b','c'],options:{profiles:{b:{x:300,width:960}},screen:'fixture',game_preferences:{mute_all:false,skip_intro:null,lowest_graphics:true}}};
let seq=0,calls=[],clock=100;
const q=createLaunchQueue({now:()=>clock,token:()=>`attempt-${++seq}`,preflight:async()=>{},dispatch:async(id,token,context)=>{calls.push({id,token,context});if(id==='b'&&calls.filter(x=>x.id==='b').length===1)throw Error('fixture failure');return id==='c'?{focused:true}:{};}});
await q.run(['a','b','c'],ctx);
assert.deepEqual(q.snapshot().items.map(x=>x.status),['submitted','failed','ready']);
await assert.rejects(q.run(['z'],ctx),/当前队列/);
let rows=q.snapshot().items;
q.reconcile({a:{phase:'ready',request_id:'stale'}});assert.equal(q.snapshot().items[0].status,'submitted');
q.reconcile({a:{phase:'ready',request_id:rows[0].token}});assert.equal(q.snapshot().items[0].status,'ready');
ctx.options.profiles.b.width=1;
const oldB=rows[1].token;
await q.retry();assert.deepEqual(calls.map(x=>x.id),['a','b','c','b']);
assert.deepEqual(calls.at(-1).context.layoutIds,['a','b','c']);assert.equal(calls.at(-1).context.options.profiles.b.width,960);assert.deepEqual(calls.at(-1).context.options.game_preferences,{mute_all:false,skip_intro:null,lowest_graphics:true});
q.reconcile({b:{phase:'failed',request_id:oldB,error:'stale'}});assert.equal(q.snapshot().items[1].status,'submitted');
q.reconcile({b:{phase:'ready',request_id:q.snapshot().items[1].token}});assert.equal(q.snapshot().items[1].status,'ready');
assert(q.clear());assert.equal(q.snapshot().items.length,0);
// Cancelling a long gap does not submit the following roles or close the first.
let entered,signalSleep;const sleeping=new Promise(r=>entered=r);calls=[];
const delayQueue=createLaunchQueue({preflight:async()=>{},dispatch:async id=>{calls.push(id);return{}},sleep:(_ms,signal)=>new Promise(resolve=>{signalSleep=signal;signal.addEventListener('abort',()=>resolve(false),{once:true});entered();})});
const delayed=delayQueue.run(['a','b','c'],{...ctx,delay:300});await sleeping;delayQueue.stop();await delayed;
assert(signalSleep.aborted);assert.deepEqual(calls,['a']);assert.deepEqual(delayQueue.snapshot().items.map(x=>x.status),['submitted','cancelled','cancelled']);
// Stopping while an API request is in flight still monitors that submitted game.
let submit,started;const inFlight=new Promise(r=>started=r);calls=[];
const inflight=createLaunchQueue({preflight:async()=>{},dispatch:id=>{calls.push(id);started();return new Promise(r=>submit=r)}});
const run=inflight.run(['a','b'],ctx);await inFlight;inflight.stop();submit({});await run;
assert.deepEqual(calls,['a']);assert(inflight.busy());const item=inflight.snapshot().items[0];
inflight.reconcile({a:{phase:'cancelled',request_id:item.token}});assert(!inflight.busy());
// Preflight fails before any launch, and an unready submitted request times out.
let preflightFail=true;calls=[];
const fail=createLaunchQueue({now:()=>clock,preflight:async()=>{if(preflightFail)throw Error('preflight failed')},dispatch:async id=>{calls.push(id);return {}}});
await fail.run(['a','b'],ctx);assert.equal(calls.length,0);assert(fail.snapshot().items.every(x=>x.status==='failed'));
preflightFail=false;await fail.retry();clock+=180001;fail.reconcile({});assert(fail.snapshot().items.every(x=>x.status==='failed'));
const abort=new AbortController();const wait=abortableDelay(300000,abort.signal);abort.abort();assert.equal(await wait,false);
console.log('PASS: separate submission/readiness; stale results ignored; failed-only retry keeps original layout; stop during long delay/API request; existing windows reused; preflight before dispatch; timeout and cancellable timer. No game/API calls.');
