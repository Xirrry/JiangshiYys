import json,sys,time,uuid,threading
try:
 import Globals
 p=Globals.player1
 role_key=str(p.server_id)+':'+str(p.short_id)
 old=getattr(Globals,'_yys_checklist_support_query',None)
 if isinstance(old,dict):
  if old.get('timer'):old['timer'].cancel()
  if old.get('observer') and old.get('callback'):
   try:old['observer'].unregister_once('look_all_help_hero_cb',old['callback'])
   except Exception:pass
 method=getattr(Globals.uiMgr.listenNetWorkMsg,'__func__',Globals.uiMgr.listenNetWorkMsg)
 observer=method.__globals__['NetWorkObserver'].instance()
 state={'nonce':uuid.uuid4().hex,'role':role_key,'started':time.time(),'ready':False,'expired':False}
 def received(data,state=state,Globals=Globals,time=time):
  try:
   if state['expired']:return
   if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=state['role']:return
   info=data.get('help_info') if hasattr(data,'get') else None
   count=info.get('be_used_times') if hasattr(info,'get') else None
   if type(count) is int and count>=0:state.update(ready=True,count=count,at=time.time())
  finally:
   timer=state.get('timer')
   if timer:timer.cancel()
 def expire(state=state,observer=observer,received=received):
  state['expired']=True
  try:observer.unregister_once('look_all_help_hero_cb',received)
  except Exception:pass
 timer=threading.Timer(7.0,expire);timer.daemon=True
 state.update(observer=observer,callback=received,timer=timer)
 Globals._yys_checklist_support_query=state
 observer.register_once('look_all_help_hero_cb',received)
 timer.start()
 # Refresh only the local friend's prayer list; never initiate or collect a prayer.
 old_prayer=getattr(Globals,'_yys_checklist_prayer_query',{})
 if old_prayer.get('timer'):old_prayer['timer'].cancel()
 if old_prayer.get('callback'):
  try:observer.unregister_once('query_friend_beg_cb',old_prayer['callback'])
  except Exception:pass
 prayer_state={'nonce':state['nonce'],'role':role_key,'ready':False,'expired':False}
 def prayer_received(data,ps=prayer_state,Globals=Globals):
  if ps['expired'] or str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=ps['role']:return
  if not hasattr(data,'get') or data.get('ret')!=0 or data.get('is_global') is not False:return
  infos=data.get('beg_infos')
  if not hasattr(infos,'items'):return
  own=str(getattr(Globals.player1,'_id',None) or getattr(Globals.player1,'id',None))
  own_rows=next((rows for key,rows in infos.items() if str(key)==own),None)
  row=own_rows.get(1,own_rows.get('1')) if hasattr(own_rows,'get') else None
  ps.update(ready=True,row={k:row.get(k) for k in ('process','need_count','book_id','beg_day')} if hasattr(row,'get') else None)
  ps['timer'].cancel()
 def prayer_expire(ps=prayer_state,observer=observer,callback=prayer_received):
  ps['expired']=True
  try:observer.unregister_once('query_friend_beg_cb',callback)
  except Exception:pass
 pt=threading.Timer(7.0,prayer_expire);pt.daemon=True
 prayer_state.update(timer=pt,callback=prayer_received);Globals._yys_checklist_prayer_query=prayer_state
 observer.register_once('query_friend_beg_cb',prayer_received);pt.start()
 p.query_friend_beg(False)
 # Request settled personal guild-boss results without opening a panel.
 old_boss=getattr(Globals,'_yys_checklist_boss_query',{})
 if old_boss.get('timer'):old_boss['timer'].cancel()
 if old_boss.get('base_callback'):
  try:observer.unregister_once('get_leader_retreat_baseinfo_cb',old_boss['base_callback'])
  except Exception:pass
 if old_boss.get('callback'):
  try:observer.unregister_once('get_leader_retreat_result_cb',old_boss['callback'])
  except Exception:pass
 bs={'nonce':state['nonce'],'role':role_key,'ready':False,'expired':False}
 def boss_received(data,bs=bs,Globals=Globals):
  if bs['expired'] or str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=bs['role']:return
  info=data.get('info') if hasattr(data,'get') else None
  if not hasattr(info,'get'):return
  own=str(getattr(Globals.player1,'_id',None) or getattr(Globals.player1,'id',None))
  ranks=info.get('rankinfo',[]);battle=info.get('battle_result',{})
  matches=[x for x in ranks if hasattr(x,'get') and str(x.get('id'))==own] if isinstance(ranks,(list,tuple)) else []
  bs.update(ready=True)
  if hasattr(battle,'get') and battle.get('is_win') is True and len(matches)==1:
   damage=matches[0].get('hurt');rank=matches[0].get('rank')
   if type(damage) in (int,float) and damage>0:bs.update(damage=damage,rank=rank)
  if bs.get('base_ready'):bs['timer'].cancel()
 def boss_base_received(data,bs=bs,Globals=Globals):
  if bs['expired'] or str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=bs['role']:return
  info=data.get('info') if hasattr(data,'get') else None
  if not hasattr(info,'get'):return
  rewards=info.get('retreat_rewards')
  bs.update(base_ready=True)
  if hasattr(rewards,'items'):
   waves=[]
   for key,items in rewards.items():
    if key in ('turn_1_reward','turn_2_reward','turn_3_reward') and isinstance(items,(list,tuple)) and any(isinstance(item,(list,tuple)) and len(item)==2 and type(item[1]) in (int,float) and item[1]>0 for item in items):waves.append(key)
   bs['pending_waves']=len(waves)
  if bs.get('ready'):bs['timer'].cancel()
 def boss_expire(bs=bs,observer=observer,cb=boss_received):
  bs['expired']=True
  try:observer.unregister_once('get_leader_retreat_baseinfo_cb',bs.get('base_callback'))
  except Exception:pass
  try:observer.unregister_once('get_leader_retreat_result_cb',cb)
  except Exception:pass
 bt=threading.Timer(7.0,boss_expire);bt.daemon=True;bs.update(timer=bt,callback=boss_received,base_callback=boss_base_received)
 Globals._yys_checklist_boss_query=bs;observer.register_once('get_leader_retreat_result_cb',boss_received);bt.start()
 observer.register_once('get_leader_retreat_baseinfo_cb',boss_base_received)
 p.get_leader_retreat_baseinfo()
 p.get_leader_retreat_result()
 p.look_all_help_hero()
 # Refresh personal Yin-gate progress, never start combat or collect rewards.
 old_gve=getattr(Globals,'_yys_checklist_gve_query',{})
 if old_gve.get('timer'):old_gve['timer'].cancel()
 if old_gve.get('callback'):
  try:observer.unregister_once('guild_get_fighted_cb',old_gve['callback'])
  except Exception:pass
 gs={'nonce':state['nonce'],'role':role_key,'ready':False,'at':time.time()}
 def gve_received(data,gs=gs,Globals=Globals,time=time):
  if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=gs['role']:return
  floor=data.get('round') if hasattr(data,'get') else None
  battles=data.get('battle_times') if hasattr(data,'get') else None
  if type(floor) is int and 0<=floor<=1000 and type(battles) is int and battles>=0:
   gs.update(ready=True,floor=floor,battles=battles,at=time.time())
   gs['timer'].cancel()
 def gve_expire(gs=gs,observer=observer,callback=gve_received):
  try:observer.unregister_once('guild_get_fighted_cb',callback)
  except Exception:pass
 gt=threading.Timer(7.0,gve_expire);gt.daemon=True
 gs.update(timer=gt,callback=gve_received);Globals._yys_checklist_gve_query=gs
 observer.register_once('guild_get_fighted_cb',gve_received);gt.start();p.guild_get_fighted()
 # Read experience/gold remaining attempts; no dungeon entry or reward claim.
 old_resource=getattr(Globals,'_yys_checklist_resource_query',{})
 if old_resource.get('timer'):old_resource['timer'].cancel()
 if old_resource.get('callback'):
  try:observer.unregister_once('query_lazy_cd_list_cb',old_resource['callback'])
  except Exception:pass
 rs={'nonce':state['nonce'],'role':role_key,'ready':False,'at':time.time()}
 def resource_received(data,rs=rs,Globals=Globals,time=time):
  if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=rs['role']:return
  cds=data.get('data') if hasattr(data,'get') else None
  if not hasattr(cds,'get'):return
  values={}
  for mode in (1,2):
   row=cds.get(str(mode),cds.get(mode));left=row.get('v') if hasattr(row,'get') else None
   if type(left) is not int or not 0<=left<=2:return
   values[str(mode)]=left
  rs.update(ready=True,values=values,at=time.time());rs['timer'].cancel()
 def resource_expire(observer=observer,cb=resource_received):
  try:observer.unregister_once('query_lazy_cd_list_cb',cb)
  except Exception:pass
 rt=threading.Timer(7.0,resource_expire);rt.daemon=True;rs.update(timer=rt,callback=resource_received)
 Globals._yys_checklist_resource_query=rs;observer.register_once('query_lazy_cd_list_cb',resource_received)
 rt.start();p.get_gold_exp_lazy_cds([1,2])
 # Read the current day's five mentoring-practice uses, not lifetime fb_times.
 old_mentor=getattr(Globals,'_yys_checklist_mentor_query',{})
 if old_mentor.get('timer'):old_mentor['timer'].cancel()
 if old_mentor.get('callback'):
  try:observer.unregister_once('shitu_fb_times_info_cb',old_mentor['callback'])
  except Exception:pass
 if old_mentor.get('relation_callback'):
  try:observer.unregister_once('shitu_get_shitu_cb',old_mentor['relation_callback'])
  except Exception:pass
 if old_mentor.get('points_callback'):
  try:observer.unregister_once('shitu_get_student_taskinfo_cb',old_mentor['points_callback'])
  except Exception:pass
 ms={'nonce':state['nonce'],'role':role_key,'ready':False,'count_ready':False,'relation_ready':False,'at':time.time()}
 def mentor_points_received(data,ms=ms,Globals=Globals,time=time):
  if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=ms['role']:return
  info=data.get('result') if hasattr(data,'get') else None
  if not hasattr(info,'get') or info.get('student_entityid')!=ms.get('student_id'):return
  points=info.get('exp_value')
  if type(points) is not int or points<0:return
  ms.update(points=points,points_ready=True,at=time.time())
  ms['ready']=ms['count_ready'] and ms['relation_ready']
  if ms['ready']:ms['timer'].cancel()
 def mentor_relation_received(data,ms=ms,Globals=Globals,time=time):
  if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=ms['role']:return
  info=data.get('result') if hasattr(data,'get') else None
  if not hasattr(info,'get') or type(info.get('level')) is not int:return
  student=info.get('cur_student',{})
  if not hasattr(student,'get'):return
  start=student.get('start_time') if student.get('entityid') else info.get('establish_cd',0)
  from module.mentoring_v3 import MentoringLogic
  hours=MentoringLogic.get_constant(51)
  if type(start) not in (int,float) or start<0 or type(hours) not in (int,float) or hours!=96:return
  ms.update(relation_ready=True,start=start,end=start+hours*3600 if start else 0,occupied=bool(student.get('entityid')),relation_state=info.get('identity'),points=None,points_ready=False,at=time.time())
  if student.get('entityid'):
   ms['student_id']=student['entityid']
   observer.register_once('shitu_get_student_taskinfo_cb',mentor_points_received)
   p.shitu_get_student_taskinfo(ms['student_id'],use_rpc_cache=False)
  else:
   ms['points']=info.get('exp_value') if info.get('identity')==2 else None
   ms['points_ready']=True
  ms['ready']=ms['count_ready'] and ms['points_ready']
  if ms['ready']:ms['timer'].cancel()
 def mentor_received(data,ms=ms,Globals=Globals,time=time):
  if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=ms['role']:return
  count=data.get('fb_day_times') if hasattr(data,'get') else None
  if type(count) is int and 0<=count<=5:
   ms.update(count_ready=True,count=count,at=time.time());ms['ready']=ms['relation_ready'] and ms.get('points_ready',False)
   if ms['ready']:ms['timer'].cancel()
 def mentor_expire(observer=observer,cb=mentor_received,relation_cb=mentor_relation_received,points_cb=mentor_points_received):
  try:observer.unregister_once('shitu_get_student_taskinfo_cb',points_cb)
  except Exception:pass
  try:observer.unregister_once('shitu_get_shitu_cb',relation_cb)
  except Exception:pass
  try:observer.unregister_once('shitu_fb_times_info_cb',cb)
  except Exception:pass
 mt=threading.Timer(7.0,mentor_expire);mt.daemon=True;ms.update(timer=mt,callback=mentor_received,relation_callback=mentor_relation_received,points_callback=mentor_points_received)
 Globals._yys_checklist_mentor_query=ms;observer.register_once('shitu_fb_times_info_cb',mentor_received)
 observer.register_once('shitu_get_shitu_cb',mentor_relation_received)
 mt.start();p.shitu_fb_times_info();p.shitu_get_shitu()
 # Weekly guild opening count is separate from this player's dinner entries.
 try:
  old_bq=getattr(Globals,'_yys_checklist_banquet_query',{})
  if old_bq.get('timer'):old_bq['timer'].cancel()
  if old_bq.get('callback'):
   try:observer.unregister_once('get_dinner_info_cb',old_bq['callback'])
   except Exception:pass
  bq={'nonce':state['nonce'],'role':role_key,'ready':False,'at':time.time()}
  def banquet_received(data,bq=bq,Globals=Globals,time=time):
   if str(Globals.player1.server_id)+':'+str(Globals.player1.short_id)!=bq['role']:return
   count=data.get('weekly_dinner_times') if hasattr(data,'get') else None
   if type(count) is int and 0<=count<=2:bq.update(ready=True,opened=count,at=time.time());bq['timer'].cancel()
  def banquet_expire(observer=observer,cb=banquet_received):
   try:observer.unregister_once('get_dinner_info_cb',cb)
   except Exception:pass
  bt=threading.Timer(7.0,banquet_expire);bt.daemon=True;bq.update(timer=bt,callback=banquet_received)
  Globals._yys_checklist_banquet_query=bq;observer.register_once('get_dinner_info_cb',banquet_received);bt.start();p.get_dinner_info()
 except Exception:pass
 # Refresh personal hunting evidence independently of the guild's opening status.
 try:
  old_kq=getattr(Globals,'_yys_checklist_kirin_query',{})
  if old_kq.get('timer'):old_kq['timer'].cancel()
  if old_kq.get('callback'):
   try:observer.unregister_once('guild_get_gve_v2_info_cb',old_kq['callback'])
   except Exception:pass
  kq={'nonce':state['nonce'],'role':role_key,'ready':False,'at':time.time()}
  def kirin_received(data,kq=kq,Globals=Globals,time=time):
   try:
    player=Globals.player1
    if str(player.server_id)+':'+str(player.short_id)!=kq['role']:return
    info=data.get('info') if hasattr(data,'get') else None
    members=info.get('gve_member_damage') if hasattr(info,'get') else None
    if not hasattr(members,'get'):return
    from com.param_def import ParamNameDef as KirinParams
    count=player.entity_get_param(KirinParams.GVE_BOSS_ATK_COUNT)
    if count is None:count=0
    damage=members.get(str(player.id),members.get(player.id,0))
    if type(count) is not int or not 0<=count<=100:return
    if type(damage) not in (int,float) or not 0<=damage<1e16:return
    kq.update(ready=True,count=count,damage=damage,at=time.time());kq['timer'].cancel()
   except Exception:pass
  def kirin_expire(observer=observer,cb=kirin_received):
   try:observer.unregister_once('guild_get_gve_v2_info_cb',cb)
   except Exception:pass
  kt=threading.Timer(7.0,kirin_expire);kt.daemon=True;kq.update(timer=kt,callback=kirin_received)
  Globals._yys_checklist_kirin_query=kq;observer.register_once('guild_get_gve_v2_info_cb',kirin_received);kt.start();p.guild_get_gve_v2_info()
 except Exception:pass
 result={'nonce':state['nonce'],'role':role_key,'started':True}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
