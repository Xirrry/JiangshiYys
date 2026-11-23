import json,sys,time,uuid,threading
try:
 import Globals
 p=Globals.player1;role=str(p.server_id)+':'+str(p.short_id)
 observer=Globals.uiMgr.listenNetWorkMsg.__func__.__globals__['NetWorkObserver'].instance()
 old=getattr(Globals,'_yys_weekly_shrine_query',{})
 if old.get('timer'):old['timer'].cancel()
 if old.get('treasure_callback'):
  try:observer.unregister_once('get_act_shop_data_cb',old['treasure_callback'])
  except Exception:pass
 if old.get('callback'):
  try:observer.unregister_once('souljade_shop_items_cb',old['callback'])
  except Exception:pass
 state={'nonce':uuid.uuid4().hex,'role':role,'ready':False,'expired':False}
 def received(data,state=state,Globals=Globals):
  if state['expired'] or str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=state['role']:return
  shop=data.get('shop_items') if hasattr(data,'get') else None
  if not hasattr(shop,'get'):return
  kind=shop.get('item_type');begin=shop.get('begin_time')
  if type(kind) is not int or type(begin) not in (int,float) or begin<=0:return
  state.update(ready=True,kind=kind,begin=begin)
  if state.get('treasure_ready'):state['timer'].cancel()
 def treasure_received(data,state=state,Globals=Globals):
  if state['expired'] or str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=state['role']:return
  if hasattr(data,'get') and data.get('act_id')==7483 and hasattr(data.get('shop_data'),'get'):
   state['treasure_ready']=True
   if state.get('ready'):state['timer'].cancel()
 def expire(state=state,observer=observer,cb=received):
  state['expired']=True
  try:observer.unregister_once('get_act_shop_data_cb',state.get('treasure_callback'))
  except Exception:pass
  try:observer.unregister_once('souljade_shop_items_cb',cb)
  except Exception:pass
 timer=threading.Timer(7.0,expire);timer.daemon=True
 state.update(timer=timer,callback=received,treasure_callback=treasure_received);Globals._yys_weekly_shrine_query=state
 observer.register_once('souljade_shop_items_cb',received);timer.start();p.souljade_shop_items(False)
 observer.register_once('get_act_shop_data_cb',treasure_received)
 p.act_shop_logic_get_act_shop_data(7483)
 result={'nonce':state['nonce'],'role':role}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
