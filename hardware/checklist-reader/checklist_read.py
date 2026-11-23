import json,sys
try:
 import Globals
 p=Globals.player1
 result={'role':{'nickname':p.name,'short_id':p.short_id,'server_id':p.server_id},'observations':{}}
 def observation(key,current,target,claimed=None):
  if not isinstance(current,(int,float)) or not isinstance(target,(int,float)) or target<=0:return
  status='done' if claimed in (1,True) else 'claimable' if current>=target and claimed is not None else 'done' if current>=target else 'todo'
  result['observations'][key]={'status':status,'detail':str(current)+' / '+str(target)}
 # Previous-week stored rewards are independent from current task completion.
 try:
  storage=getattr(p,'reward_storage_logic',None)
  last=getattr(storage,'last_store',None)
  if hasattr(last,'get'):
   stored={}
   for module,key in [('1','w18'),('2','guild_banquet'),('3','d9'),('4','d7')]:
    row=last.get(module)
    saved=(row.get('save_num') if hasattr(row,'get') else getattr(row,'save_num',None)) if row is not None else 0
    got=(row.get('get_num') if hasattr(row,'get') else getattr(row,'get_num',None)) if row is not None else 0
    if type(saved) is int and type(got) is int and 0<=got<=saved<=10:stored[key]={'saved':saved,'received':got}
   result['_last_week_storage']=stored
 except Exception:pass
 # Only fresh personal hunting evidence may update the daily task.
 try:
  import time
  kq=getattr(Globals,'_yys_checklist_kirin_query',{})
  if kq.get('role')==str(p.server_id)+':'+str(p.short_id) and time.time()-kq.get('at',0)<30:
   result['_kirin_query']={k:kq.get(k) for k in ('role','nonce','ready')}
   if kq.get('ready'):
    count,damage=kq['count'],kq['damage']
    result['observations']['guild_kirin']={'status':'done' if count>0 or damage>0 else 'todo','detail':'今日已挑战 '+str(count)+' 次 · 个人伤害 '+format(int(damage),',')}
 except Exception:pass
 # Only the personal entry counter can complete the weekly banquet task.
 try:
  import time
  from com.param_def import ParamNameDef as DinnerParams
  entered=p.entity_get_param(DinnerParams.GUILD_DINNER_WEEKLY_TIMES)
  if type(entered) is int and 0<=entered<=2:result['observations']['guild_banquet']={'status':'done' if entered==2 else 'todo','detail':'个人本周参与 '+str(entered)+' / 2 次'}
  bq=getattr(Globals,'_yys_checklist_banquet_query',{})
  if bq.get('role')==str(p.server_id)+':'+str(p.short_id) and time.time()-bq.get('at',0)<30:result['_banquet_query']={k:bq.get(k) for k in ('role','nonce','ready','opened')}
 except Exception:pass
 # Lanqi book_cd is an absolute deadline, not the last exchange timestamp.
 try:
  import time
  from com.param_def import ParamNameDef as TradeParams
  trade=p.entity_get_param(TradeParams.OFFLINE_TRADE_TIME)
  end=trade.get('book_cd') if hasattr(trade,'get') else None
  if type(end) in (int,float) and 0<=end<10**11:
   result['observations']['lanqi_exchange']={'status':'cooldown' if end>time.time() else 'ready','detail':'兰契碎片交换冷却','exchange_end':end}
 except Exception:pass
 # Daily completion requires filling each prayer's daily quota, not lifetime auto totals.
 def part(name,row):
  result={'name':name,'status':'unknown','detail':'当前数据不足'}
  if not hasattr(row,'get'):return result
  book=row.get('book_id')
  table=getattr(getattr(sys.modules.get('DynamicConfigData'),'DATA_CURRENCY',None),'data',{})
  entry=table.get(book,table.get(str(book),{}))
  hero_name=entry.get('name') if hasattr(entry,'get') else None
  if isinstance(hero_name,str) and hero_name:result['hero_name']=hero_name.replace('(碎片)','碎片').replace('（碎片）','碎片')
  current=row.get('process');target=row.get('need_count')
  if type(current) is not int or type(target) is not int or current<0 or target<=0:return result
  result.update(status='done' if current>=target else 'active',current=current,target=target,detail='已获取 '+str(current)+' / '+str(target))
  return result
 prayer=getattr(p,'guild_beg_times',None)
 guild={'name':'寮祈愿','status':'unknown','detail':'当天进度尚未加载'}
 friend={'name':'好友祈愿','status':'unknown','detail':'本人当天进度尚未加载'}
 mod=sys.modules.get('module.guild.GuildBegHeroPanel')
 defs=getattr(getattr(mod,'param_def',None) or sys.modules.get('com.param_def'),'ParamNameDef',None)
 logic=getattr(mod,'GuildLogic',None) or sys.modules.get('module.guild.GuildLogic')
 if type(prayer) is int and prayer==0:guild.update(status='todo',detail='尚未发起')
 if type(prayer) is int and prayer==2:
  guild.update(status='active',detail='已发起，当天获赠进度尚未加载')
  if defs is not None:
   try:guild=part('寮祈愿',p.entity_get_param(defs.GUILD_BEG_REWARD))
   except Exception:pass
 # An ongoing automatic request may have been created on a previous day.
 # Its current daily reward row still supplies today's progress when UIDs match.
 if defs is not None:
  try:
   auto_key=getattr(defs,'GUILD_HERO_AUTO_BEG_INFO',None)
   auto=p.entity_get_param(auto_key) if auto_key is not None else None
   reward=p.entity_get_param(defs.GUILD_BEG_REWARD)
   if hasattr(auto,'get') and hasattr(reward,'get') and auto.get('auto_uid') and auto.get('auto_uid')==reward.get('auto_uid'):guild=part('寮祈愿',reward)
  except Exception:pass
 own=getattr(p,'_id',None) or getattr(p,'id',None)
 cache=getattr(logic,'friendBegInfo',{}) if logic else {}
 if own is not None and hasattr(cache,'get'):
  candidates=[row for row in cache.get('friend_beg_list',[]) if hasattr(row,'get') and str(row.get('id'))==str(own)]
  if len(candidates)==1:friend=part('好友祈愿',candidates[0])
 prayer_query=getattr(Globals,'_yys_checklist_prayer_query',{})
 result['_prayer_query']={k:prayer_query.get(k) for k in ('nonce','role','ready','expired')}
 if prayer_query.get('role')==str(p.server_id)+':'+str(p.short_id) and prayer_query.get('ready') and not prayer_query.get('expired'):
  friend=part('好友祈愿',prayer_query.get('row'))
  if prayer_query.get('row') is None:friend={'name':'好友祈愿','status':'todo','detail':'尚未发起'}
 parts=[guild,friend]
 state='done' if all(x['status']=='done' for x in parts) else 'active' if any(x['status'] in ('active','done') for x in parts) else 'todo' if all(x['status']=='todo' for x in parts) else 'unknown'
 result['observations']['d1']={'status':state,'detail':'分别收满寮祈愿与好友祈愿的当天额度才算完成','parts':parts}
 # Personal reset timestamps can lag behind a current task-panel snapshot.
 # Accept a fallback only when today's panel, personal counter and itemized counts agree.
 try:
  import time,datetime
  guild_module=sys.modules.get('module.guild.GuildLogic')
  param_module=getattr(guild_module,'param_def',None) or sys.modules.get('com.param_def')
  guild_defs=getattr(param_module,'ParamNameDef',None)
  if guild_defs is not None:
   count=p.entity_get_param(guild_defs.FINISHED_GUILD_TASK_TIMES)
   reset=p.entity_get_param(guild_defs.LAST_RESET_GUILD_TASK_SECS)
   current_day=datetime.datetime.utcfromtimestamp(time.time()+8*3600).date()
   def today(stamp):
    return type(stamp) in (int,float) and stamp>0 and datetime.datetime.utcfromtimestamp(stamp+8*3600).date()==current_day
   if type(count) is int and count>=0:
    valid=today(reset)
    if not valid:
     panel=getattr(guild_module,'guild_task_info',{})
     if hasattr(panel,'get') and today(panel.get('last_refresh_task_time')):
      panel_count=panel.get('guild_task_finished_times')
      stats=panel.get('day_finished_statics')
      if type(panel_count) is int and panel_count==count and isinstance(stats,(list,tuple)):
       pairs=[row for row in stats if isinstance(row,(list,tuple)) and len(row)==2 and type(row[1]) is int and row[1]>=0]
       valid=len(pairs)==len(stats) and sum(row[1] for row in pairs)==count
    if valid:observation('d5',count,30)
 except Exception:pass
 # Verified guild funds claim: SUCCESS -> BONUS_GET_BEFORE; other errors are not completion.
 try:
  funds_module=sys.modules.get('module.guild.GuildLogic')
  funds_info=getattr(funds_module,'myGuildDetail',{})
  codes=sys.modules.get('avatarmembers.GuildMember')
  if hasattr(funds_info,'get') and codes is not None:
   state=funds_info.get('avl_get_bonus')
   if type(state) is int:
    claimed=getattr(codes,'BONUS_GET_BEFORE',None)
    available=getattr(codes,'SUCCESS',None)
    insufficient=getattr(codes,'BONUS_NOT_ENOUGH',None)
    contribution=getattr(codes,'BOUNS_LACK_DONATE',None)
    amount=funds_info.get('member_bonus')
    valid_amount=type(amount) is int and amount>=0
    if type(amount) is float and amount>=0 and amount<2**53 and amount.is_integer():amount=int(amount);valid_amount=True
    formatted='{: ,}'.replace(' ','').format(amount) if valid_amount else None
    if claimed is not None and state==claimed:result['observations']['d2']={'status':'done','detail':'今日已领取资金 '+formatted if formatted is not None else '今日已领取，金额未读到'}
    elif available is not None and state==available:
     result['observations']['d2']={'status':'claimable','detail':'可领取资金 '+formatted if formatted is not None else '寮资金可领取，金额未读到'}
    elif insufficient is not None and state==insufficient:result['observations']['d2']={'status':'todo','detail':'寮资金不足，尚未领取'}
    elif contribution is not None and state==contribution:result['observations']['d2']={'status':'todo','detail':'贡献不足，尚未领取'}
 except Exception:pass
 # New daily-login gift uses its free-stage state, not legacy DAILY_GIFT_INFO changes.
 try:
  import datetime,time
  shop_module=sys.modules.get('ui.ShopManager')
  if shop_module is not None:
   manager=shop_module.getInstance()
   gift=manager.getDailyLoginRewardState()
   if hasattr(gift,'get') and gift.get('valid') is True:
    generated=gift.get('gen_time')
    if type(generated) in (int,float) and generated>0 and datetime.datetime.utcfromtimestamp(generated+8*3600).date()==datetime.datetime.utcfromtimestamp(time.time()+8*3600).date():
     claimed=gift.get('free_claimed')
     pending=getattr(manager,'_dailyLoginFreeClaimPending',False)
     if claimed is True:result['observations']['d3']={'status':'done','detail':'今日免费每日礼包已领取'}
     elif claimed is False and pending is False:result['observations']['d3']={'status':'claimable','detail':'今日免费每日礼包可领取'}
     if 'd3' in result['observations']:
      pd=getattr(shop_module,'param_def',None) or sys.modules.get('com.param_def')
      gd=getattr(pd,'ParamNameDef',None)
      if gd is not None:
       count=p.entity_get_param(gd.GROWING_GIFT_BUY_COUNT)
       gc=sys.modules.get('DynamicConfigData')
       table=getattr(getattr(gc,'DATA_GROWING_GIFT',None),'data',None)
       if table is None:table=getattr(sys.modules.get('com.data.cdata.growing_gift'),'data',None)
       cycle=len(table) if table is not None else 0
       if type(count) is int and type(cycle) is int and cycle>0 and 0<=count<=cycle:
        result['observations']['d3']['detail']+=' · '+str(count)+'/'+str(cycle)+'，距御行达摩还差 '+str(cycle-count)+' 次领取'

 except Exception:pass
 # Only accept a fresh response produced by this launcher's explicit query.
 try:
  import time,datetime
  support=getattr(Globals,'_yys_checklist_support_query',None)
  if isinstance(support,dict):
   result['_support_query']={key:support.get(key) for key in ('nonce','role','ready','expired')}
   if support.get('role')==str(p.server_id)+':'+str(p.short_id) and support.get('ready') is True and not support.get('expired'):
    age=time.time()-support.get('at',0)
    count=support.get('count')
    if 0<=age<=7 and type(count) is int and count>=0:result['observations']['d10']={'status':'done' if count>=50 else 'todo','detail':'自己的协战式神今日被使用 '+str(count)+' / 50 次'}
 except Exception:pass
 boss_query=getattr(Globals,'_yys_checklist_boss_query',{})
 result['_boss_query']={k:boss_query.get(k) for k in ('nonce','role','ready','expired')}
 result['_boss_query']['ready']=bool(boss_query.get('ready') and boss_query.get('base_ready'))
 if boss_query.get('role')==str(p.server_id)+':'+str(p.short_id) and boss_query.get('ready') and not boss_query.get('expired') and type(boss_query.get('damage')) in (int,float):
  result['_guild_boss_evidence']={k:boss_query.get(k) for k in ('damage','rank')}
 # Weekly guild-boss completion needs this player's settled result and a current-week session.
 try:
  import time,datetime
  boss_logic=sys.modules.get('module.guild.tuizhi.GuildBossLogic')
  base=getattr(boss_logic,'GUILD_BOSS_BASE_INFO',{})
  panel=Globals.uiMgr.getUI('GuildBossMainPanel')
  settled=getattr(panel,'result_info',{}) if panel else {}
  if result.get('_guild_boss_evidence'):
   ev=result['_guild_boss_evidence'];settled={'battle_result':{'is_win':True},'rankinfo':[{'id':str(getattr(p,'_id',None) or getattr(p,'id',None)),'hurt':ev['damage'],'rank':ev.get('rank')}]}
  own=getattr(p,'_id',None) or getattr(p,'id',None)
  if hasattr(base,'get') and hasattr(settled,'get') and own is not None:
   started=base.get('boss_start_time');hard=base.get('challenge_hard_lv')
   if type(started) in (int,float) and 0<started<=time.time() and type(hard) is int and hard==0:
    today=datetime.datetime.utcfromtimestamp(time.time()+8*3600).date()
    monday=today-datetime.timedelta(days=today.weekday())
    session=datetime.datetime.utcfromtimestamp(started+8*3600).date()
    battle=settled.get('battle_result',{})
    if monday<=session<=today and hasattr(battle,'get') and battle.get('is_win') is True:
     ranks=settled.get('rankinfo',[])
     if isinstance(ranks,(list,tuple)):
      matches=[row for row in ranks if hasattr(row,'get') and str(row.get('id'))==str(own)]
      if len(matches)==1:
       damage=matches[0].get('hurt');rank=matches[0].get('rank')
       if type(damage) in (int,float) and damage>0:
        detail='本周已完成 · 伤害 '+format(damage,',')
        if type(rank) is int and rank>0:detail+=' · 第 '+str(rank)+' 名'
        result['observations']['d9']={'status':'done','detail':detail}
 except Exception:pass
 # Unclaimed turn rewards are valid even after the server clears boss_start_time.
 if boss_query.get('role')==str(p.server_id)+':'+str(p.short_id) and boss_query.get('base_ready') and not boss_query.get('expired'):
  pending=boss_query.get('pending_waves')
  if type(pending) is int and pending>0:
   import datetime
   weekday=(datetime.datetime.utcnow()+datetime.timedelta(hours=8)).weekday()
   if weekday>=5:
    result['observations']['d9']={'status':'claimable','detail':'本周已完成 · '+str(pending)+' 波退治奖励待领取'}
   else:
    result['observations']['d9']={'status':'todo','detail':'上周退治奖励未领取 · '+str(pending)+' 波待领取；不计入本周完成'}
 # Only the equipped own-realm UID determines this timer, never the inventory selection.
 try:
  gl=sys.modules.get('module.guild.GuildLogic');lbs=getattr(gl,'lbs_info',None)
  slots=lbs.get('ls_cards') if hasattr(lbs,'get') else None
  if isinstance(slots,(list,tuple)):
   if not slots:result['observations']['realm_card']={'status':'card_expired','realm_card':{'start':0,'end':0,'label':''}}
   elif len(slots)==1 and isinstance(slots[0],(list,tuple)) and len(slots[0])>=2:
    logic=next((m for k,m in list(sys.modules.items()) if k.endswith('.JiejieCardDataLogic')),None)
    getter=getattr(logic,'getCardDataFromLsCards',None)
    card=getter(None) if getter else None
    uid,start=slots[0][:2];hours=getattr(card,'totalTime',None)
    config=sys.modules.get('DynamicConfigData');table=getattr(getattr(config,'DATA_JJCARD',None),'data',{})
    rule=table.get(getattr(card,'itemid',None),{})
    name=rule.get('name') if hasattr(rule,'get') else None;star=rule.get('star') if hasattr(rule,'get') else None
    if str(getattr(card,'uid',None))==str(uid) and type(start) in (int,float) and start>0 and type(hours) in (int,float) and 0<hours<=168 and isinstance(name,str) and type(star) is int and 1<=star<=6:
     end=start+hours*3600
     result['observations']['realm_card']={'status':'card_running','realm_card':{'start':start,'end':end,'label':str(star)+'星'+name}}
 except Exception:pass
 # Outgoing friend foster is a rolling timer, never a completed daily task.
 try:
  import time
  record=getattr(p,'set_other',None)
  if isinstance(record,dict):
   if not record:result['observations']['d4']={'status':'home','detail':'当前没有寄养，记得安排寄养','foster':{'end':0,'start':0,'target':''}}
   elif record.get('herouid') and record.get('frienduid'):
    realm=sys.modules.get('com.JiejieData')
    remaining=realm.getSetOtherHeroTime() if realm else None
    if type(remaining) in (int,float) and remaining>=0 and remaining<86400:
     server_now=realm.TimeManager.getServerTime()
     target='好友结界';friends=sys.modules.get('com.FriendData')
     for field in ('friendDataList','globalFriendDataList'):
      collection=getattr(friends,field,[]) if friends else []
      items=collection.values() if hasattr(collection,'values') else collection
      for item in items:
       if str(getattr(item,'uid',None))==str(record.get('frienduid')):target=getattr(item,'name',None) or target
     end=server_now+remaining
     result['observations']['d4']={'status':'fostering' if remaining>0 else 'home','detail':'正在好友结界寄养' if remaining>0 else '寄养回家了，记得再次寄养','foster':{'start':record.get('t',0),'end':end,'target':target}}
 except Exception:pass
 # Current weekly secret floors are next-unlocked floors; historical race times are excluded.
 try:
  import datetime
  secret=sys.modules.get('module.highmiwen.HighMiwenLogic')
  secret_defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  secret_key=getattr(secret_defs,'ADVANCED_FLOOE',None)
  if secret and secret_key is not None:
   season=secret.get_open_highmiwen_race_data();active=secret.getCurOpenHighMiwenFbs()
   floors=p.entity_get_param(secret_key)
   if floors is None:floors={}
   if hasattr(season,'get') and hasattr(floors,'get') and isinstance(active,(list,tuple)) and active:
    begin=season.get('begin_time');end=season.get('end_time')
    now=datetime.datetime.utcnow()+datetime.timedelta(hours=8)
    if isinstance(begin,(list,tuple)) and isinstance(end,(list,tuple)) and datetime.datetime(*begin[:6])<=now<datetime.datetime(*end[:6]):
     sections=[];counts=[]
     for fb in active:
      if fb not in (season.get('fb1'),season.get('fb2')):raise ValueError('Season mismatch')
      raw=floors.get(str(fb),floors.get(fb,1))
      if type(raw) is not int or not 1<=raw<=11:raise ValueError('Invalid secret floor')
      info=secret.getHighFbInfoByFbty(fb)
      title=info.get('title') if hasattr(info,'get') else None
      if not isinstance(title,str):raise ValueError('Missing secret title')
      count=raw-1;counts.append(count);sections.append(title+' '+str(count)+' / 10 层')
     result['observations']['w5']={'status':'done' if all(x==10 for x in counts) else 'todo','detail':'本周秘闻 · '+'；'.join(sections)}
 except Exception:pass
 # Atlas and daily-sign sharing use the same weekly reward flag.
 try:
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  key=getattr(defs,'SHARD_RECORD',None)
  shares=p.entity_get_param(key) if key is not None else None
  shared=shares.get('week_shard') if hasattr(shares,'get') else None
  if type(shared) is bool:
   result['observations']['w6']={'status':'done' if shared else 'todo','detail':'本周分享奖励已获得（图鉴、签到分享均可）' if shared else '本周分享奖励尚未获得（图鉴、签到分享均可）'}
 except Exception:pass
 # Secret share is independent of atlas and area-king sharing.
 try:
  share_defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  share_key=getattr(share_defs,'SHARD_RECORD',None)
  shares=p.entity_get_param(share_key) if share_key is not None else None
  secret_shared=shares.get('advanced_shared') if hasattr(shares,'get') else None
  if type(secret_shared) is bool:
   result['observations']['w7']={'status':'done' if secret_shared else 'todo','detail':'本周秘闻已分享并获得奖励' if secret_shared else '本周尚未完成秘闻分享'}
 except Exception:pass
 # Weekly area-king share uses its own reward flag, independent of other shares.
 try:
  share_defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  share_key=getattr(share_defs,'SHARD_RECORD',None)
  share_record=p.entity_get_param(share_key) if share_key is not None else None
  shared=share_record.get('lbs_shard') if hasattr(share_record,'get') else None
  if type(shared) is bool:
   result['observations']['w8']={'status':'done' if shared else 'todo','detail':'本周地域鬼王已分享并获得奖励' if shared else '本周尚未完成地域鬼王分享'}
 except Exception:pass
 # Area king progress is distinct daily bosses, not the daily activity task.
 try:
  area=sys.modules.get('module.areaking.AreaKingLogic')
  if area:
   slots=area.getTodayFightBossList();maximum=area.getTodayMaxBossCount()
   if isinstance(slots,(list,tuple)) and type(maximum) in (int,float) and 0<maximum<=20 and int(maximum)==maximum:
    opened=[x for x in slots if hasattr(x,'get') and x.get('openf') is True]
    if len(opened)==int(maximum):
     finished=[];valid=True
     for slot in opened:
      boss=slot.get('boss')
      if boss is None:continue
      if not hasattr(boss,'get') or not boss.get('boss_id') or not boss.get('battleid'):valid=False;break
      finished.append(str(boss['boss_id']))
     if valid and len(set(finished))==len(finished):
      count=len(finished);target=int(maximum)
      result['observations']['d6']={'status':'done' if count>=target else 'todo','detail':'今日已挑战 '+str(count)+' / '+str(target)+' 只地域鬼王'}
 except Exception:pass
 # The mentoring daily count must come from this session's read-only refresh.
 try:
  import time
  ms=getattr(Globals,'_yys_checklist_mentor_query',{})
  result['_mentor_query']={k:ms.get(k) for k in ('nonce','role','ready')}
  if ms.get('role')==str(p.server_id)+':'+str(p.short_id) and ms.get('ready') and 0<=time.time()-ms.get('at',0)<30:
   count=ms.get('count')
   if type(count) is int and 0<=count<=5:result['observations']['mentoring_practice']={'status':'done' if count==5 else 'todo','detail':'今日守护历练 '+str(count)+' / 5 次 · 剩余 '+str(5-count)+' 次'}
   if ms.get('relation_ready'):
    points=ms.get('points')
    if type(points) is int and points>=0:
     result['observations']['mentoring_points']={'status':'target_met' if points>=2000 else 'progressing','detail':'当前师徒历练点数 '+format(points,',')+' / 2,000'}
    meta={k:ms.get(k) for k in ('start','end','occupied','relation_state')}
    result['observations']['mentoring_recruit']={'status':'cooldown' if meta['end']>time.time() else 'occupied' if meta['occupied'] else 'ready' if meta['start'] else 'inactive','detail':'收徒冷却','mentoring':meta}

 except Exception:pass
 # Six Realms blessing is an inventory item, not a weekly clear/reward-claim flag.
 try:
  count=p.getCurrency(601027)
  if type(count) is int and 0<=count<=999999:
   result['observations']['w15']={'status':'done' if count==0 else 'todo','detail':'万相赐福剩余 '+str(count)+' 个'+(' · 已用完' if count==0 else ' · 通关时可获得额外奖励')}
 except Exception:pass
 # Eternal Sea shares a weekly counter table, but only h13 counts its doubled rewards.
 try:
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  key=getattr(defs,'Dungeon_rune_WEEK_COUNT',None)
  weekly=p.entity_get_param(key,{}) if key is not None else None
  cfg=sys.modules.get('DynamicConfigData');table=getattr(getattr(cfg,'DATA_HUN13_CONST',None),'data',{})
  raw=table.get(13,table.get('13',{})).get('value')
  limit=int(raw) if type(raw) is int or isinstance(raw,str) and raw.isdigit() else None
  if hasattr(weekly,'get') and type(limit) is int and 0<limit<=10000:
   used=weekly.get('h13',0)
   if type(used) is int and 0<=used<=limit:
    switch=p.entity_get_param('hun13',{})
    off=hasattr(switch,'get') and switch.get('b')==0
    result['observations']['w17']={'status':'done' if used>=limit else 'todo','detail':'本周奖励翻倍已用 '+str(used)+' / '+str(limit)+' 次 · 剩余 '+str(limit-used)+' 次'+(' · 翻倍开关已关闭' if off else '')}
 except Exception:pass
 # Fresh lazy-CD values are remaining attempts, not lifetime or old-day cts counters.
 try:
  import time
  rs=getattr(Globals,'_yys_checklist_resource_query',{})
  result['_resource_query']={k:rs.get(k) for k in ('nonce','role','ready')}
  if rs.get('role')==str(p.server_id)+':'+str(p.short_id) and rs.get('ready') and 0<=time.time()-rs.get('at',0)<30:
   for mode,task,label in ((1,'d13','经验妖怪'),(2,'d12','金币妖怪')):
    left=rs.get('values',{}).get(str(mode))
    if type(left) is int and 0<=left<=2:
     result['observations'][task]={'status':'done' if left==0 else 'todo','detail':label+'剩余 '+str(left)+' / 2 次 · 0点、12点刷新'}
 except Exception:pass
 # Daily boss progress must exhaust the actual quota, including carried attempts.
 try:
  from module.free_fengmo import FreeFengmoLogic as FreeBoss
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  if FreeBoss.is_act_open():
   weekday=FreeBoss.get_today_weekday()
   caps=p.entity_get_param(defs.FREE_FENGMO_WEEK_CAN_ATTACK)
   attacked=p.entity_get_param(defs.FREE_FENGMO_ATTACKED)
   total=caps.get(str(weekday),caps.get(weekday)) if hasattr(caps,'get') else None
   if attacked is None:attacked=[]
   if type(total) is int and 0<=total<=100 and isinstance(attacked,(list,tuple)):
    current=len(attacked);remaining=max(0,total-current)
    result['observations']['evening_boss']={'status':'done' if remaining==0 else 'todo','detail':'今日逢魔 Boss 已打 '+str(current)+' / '+str(total)+' 次 · 剩余 '+str(remaining)+' 次'}
  else:
   key=getattr(defs,'EVENING_BIG_BOSS_FINISHED',None)
   finished=p.entity_get_param(key,0) if key is not None else None
   if type(finished) is int and finished in (0,1):
    result['observations']['evening_boss']={'status':'done' if finished else 'todo','detail':'今日逢魔 Boss 战斗 '+str(finished)+' / 1 次'}
 except Exception:pass
 # The live query returns today's round; history_round is deliberately ignored.
 try:
  import time
  gs=getattr(Globals,'_yys_checklist_gve_query',{})
  result['_gve_query']={k:gs.get(k) for k in ('nonce','role','ready')}
  if gs.get('role')==str(p.server_id)+':'+str(p.short_id) and gs.get('ready') and 0<=time.time()-gs.get('at',0)<30:
   floor=gs.get('floor');battles=gs.get('battles')
   if type(floor) is int and 0<=floor<=1000 and type(battles) is int and battles>=0:
    result['observations']['d7']={'status':'done' if floor>=70 else 'todo','detail':'今日阴界之门 '+str(floor)+' / 70 层 · 已挑战 '+str(battles)+' 次'}
 except Exception:pass
 # Real-world discoveries have their own daily quota; one click can use all four.
 try:
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  key=getattr(defs,'EVENING_EVENT_COUNT',None)
  # Before the first visit the record is absent; the untouched quota is four.
  remaining=p.entity_get_param(key,4) if key is not None else None
  cfg=sys.modules.get('DynamicConfigData');table=getattr(getattr(cfg,'DATA_CONSTANT',None),'data',{})
  values=table.get(193,table.get('193',{})).get('value')
  if isinstance(values,(list,tuple)) and values:
   maximum=values[0]
   if type(maximum) in (int,float) and maximum==4 and type(remaining) is int and 0<=remaining<=maximum:
    used=int(maximum)-remaining
    result['observations']['d8']={'status':'done' if used==4 else 'todo','detail':'今日现世逢魔 '+str(used)+' / 4 次'}
 except Exception:pass
 # Pact shop random souls: use current weekly remainder, never lifetime totals.
 try:
  aes=sys.modules.get('com.activity.ActivityEventSystem')
  act=aes.ActivityEventSystem.instance()._get_activity_by_shop_id(8600) if aes else None
  comp=act.get_comp('ShopComp') if act else None
  info=getattr(comp,'shop_info',None)
  if hasattr(info,'get') and hasattr(info.get('goods'),'get'):
   rows=comp.get_shop_data()
   for row in rows:
    if row.get('id')!=7703 or row.get('currency_id')!=900624:continue
    limit=row.get('weeklimit');remaining=row.get('left_num')
    if type(limit) is int and limit==100 and type(remaining) is int and 0<=remaining<=limit and row.get('left_num_limit')=='week_left_limit':
     used=limit-remaining
     detail='本周已兑换御魂 '+str(used)+' / '+str(limit)+' 次 · 剩余 '+str(remaining)+' 次'
     if remaining:
      costs=row.get('formula',[])
      if len(costs)==1 and len(costs[0])==2 and costs[0][0]==900622 and type(costs[0][1]) in (int,float) and costs[0][1]>0:
       try:balance=p.getCurrency(900622)
       except Exception:balance=None
       need=remaining*costs[0][1]
       if type(balance) in (int,float) and balance>=0:
        detail+=' · 契忆 '+format(balance,',.0f')+' / 换完需 '+format(need,',.0f')
        if balance<need:detail+=' · 需要战斗刷取，还差 '+format(need-balance,',.0f')+' 契忆'
       else:detail+=' · 契忆余额未读到'
      else:detail+=' · 兑换消耗未读到'
     result['observations']['pact_shop_souls']={'status':'done' if used==limit else 'todo','detail':detail}
 except Exception:pass
 # True Orochi reward uses are separate from saved waves, pity and hoarded rewards.
 try:
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  key=getattr(defs,'ZHENBAQIDASHE_CTRL',None)
  record=p.entity_get_param(key) if key is not None else None
  cfg=sys.modules.get('DynamicConfigData')
  table=getattr(getattr(cfg,'DATA_CONSTANT',None),'data',{})
  row=table.get(238,table.get('238',{}));values=row.get('value')
  if hasattr(record,'get') and isinstance(values,(list,tuple)) and values:
   limit=values[0];used=record.get('xz',0)
   if type(limit) in (int,float) and 0<limit<=100 and int(limit)==limit and type(used) is int and 0<=used<=limit:
    limit=int(limit)
    result['observations']['w18']={'status':'done' if used>=limit else 'todo','detail':'本周已获取奖励 '+str(used)+' / '+str(limit)+' 次 · 剩余 '+str(limit-used)+' 次'}
 except Exception:pass
 # Weekly ranked wins and earned honor are distinct from streaks and wallet balances.
 try:
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  key=getattr(defs,'SYNC_PVP_WON_WEEKLY',None)
  wins=p.entity_get_param(key,0) if key is not None else None
  if type(wins) is int and wins>=0:
   result['observations']['w19']={'status':'done' if wins>=5 else 'todo','detail':'本周斗技已胜 '+str(wins)+' / 5 场'}
 except Exception:pass
 try:
  earned=getattr(p,'honor_score_this_week',None)
  score=getattr(p,'pvp_score',None);previous=getattr(p,'last_week_pvp_stage',None)
  logic=sys.modules.get('com.PvpData')
  current=logic.score2stage(score) if logic and type(score) in (int,float) else None
  cfg=sys.modules.get('DynamicConfigData')
  if type(earned) is int and earned>=0 and type(current) is int and type(previous) is int and 1<=current<=11 and 0<=previous<=11:
   stage=max(current,previous)
   table_name='DATA_PVP_MASTER' if stage>=10 else 'DATA_PVP'
   table=getattr(getattr(cfg,table_name,None),'data',{})
   row=table.get(stage,table.get(str(stage),{}));limit=row.get('honor_limit')
   if type(limit) in (int,float) and limit>0 and int(limit)==limit:
    result['observations']['w20']={'status':'done' if earned>=limit else 'todo','detail':'本周已获取荣誉 '+format(earned,',')+' / '+format(int(limit),',')}
 except Exception:pass
 config=sys.modules.get('DynamicConfigData')
 def lookup(table,key):return table.get(key,table.get(str(key)))
 god=getattr(getattr(config,'DATA_GODAPP_TASK2',None),'data',{})
 for identity,key in [(201,'d0'),(202,'w0'),(203,'w1'),(205,'w2'),(204,'w3'),(206,'w4')]:
  row=lookup(getattr(p,'godapp_task',{}),identity)
  cfg=lookup(god,identity) or {}
  if row is not None:observation(key,row.get('process'),cfg.get('condition'),row.get('got_reward'))
 daily=getattr(p,'daily_task',{})
 for identity,key,target in []:
  row=lookup(daily,identity)
  if row is not None:observation(key,row.get('cur_times'),target)
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
