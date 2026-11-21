import json,sys
try:
 import Globals
 def clean(v,depth=0):
  if depth>5:return None
  if v is None or isinstance(v,(bool,int,float)):return v
  if isinstance(v,bytes):
   try:return v.decode('utf-8')
   except UnicodeError:return v.decode('gb18030','replace')
  if isinstance(v,str) or type(v).__name__ in ('unicode','long'):return v
  if isinstance(v,dict):return dict((clean(k,depth+1),clean(x,depth+1)) for k,x in list(v.items())[:100])
  if isinstance(v,(list,tuple)):return [clean(x,depth+1) for x in v[:100]]
  return None
 def fields(v):
  if isinstance(v,dict):return v
  return getattr(v,'__dict__',{})
 p=Globals.player1
 m=sys.modules.get('ui.monsterhunt.MonsterHuntMgr')
 mgr=fields(getattr(m,'m_instance',None))
 if 'taskcache' not in mgr:raise ValueError('Bounty cache not loaded')
 cache=mgr.get('taskcache')
 if not isinstance(cache,dict):raise ValueError('Bounty cache format unsupported')
 details={}
 for value in mgr.get('_lastTaskProgress',{}).values():
  td=fields(value.get('taskData'))
  uid=td.get('_task_uid',td.get('_pos_id'))
  if uid:details[str(uid)]=td
 def rewards(values):
  result=[]
  config=sys.modules.get('DynamicConfigData')
  table=getattr(getattr(config,'DATA_CURRENCY',None),'data',{})
  for value in values or []:
   if not isinstance(value,(list,tuple)) or len(value)<2:continue
   item,amount=value[:2]
   row=table.get(item,table.get(str(item),{}))
   name=clean(row.get('name')) if row else None
   if item in (900173,900174,900175) and amount==0:amount=None
   result.append({'item_id':item,'name':name or 'Reward','count':amount})
  return result
 def monster_name(identity):
  if not identity:return None
  config=sys.modules.get('DynamicConfigData')
  table=getattr(getattr(config,'DATA_HERO',None),'data',{})
  row=table.get(identity,table.get(str(identity),{}))
  return clean(row.get('name')) if row else None
 rows=[]
 own_id=getattr(p,'_id',None) or getattr(p,'id',None)
 for uid,t in list(cache.items())[:100]:
  t=fields(t);td=details.get(str(uid),{})
  members=[]
  for identity,part in sorted(t.get('players',{}).items(),key=lambda item:item[1].get('index',0)):
   label=None
   if own_id is not None:label='self' if str(identity)==str(own_id) else 'friend'
   elif isinstance(td.get('_isStartByMe'),bool):
    mine=1 if td['_isStartByMe'] else 2
    label='self' if part.get('index')==mine else 'friend'
   members.append({'label':label,'index':part.get('index'),'current':part.get('process'),'target':part.get('need_val'),'monster':monster_name(part.get('cond_val') or td.get('_cur_kill_id_'+str(part.get('index'))))})
  if t.get('type') in (3,7,9):
   for index in (1,2):
    if any(member['index']==index for member in members):continue
    target=td.get('_target_kill_num_'+str(index))
    if not target:continue
    mine=1 if td.get('_isStartByMe') is True else 2 if td.get('_isStartByMe') is False else None
    members.append({'label':('self' if index==mine else 'friend') if mine else None,'index':index,'current':td.get('_cur_kill_num_'+str(index)),'target':target,'monster':monster_name(td.get('_cur_kill_id_'+str(index)))})
   members.sort(key=lambda member:member['index'] or 0)
  rows.append({'uid':clean(uid),'task_id':t.get('id'),'kind':t.get('type'),'name':clean(td.get('_taskName')),
   'current':t.get('process'),'target':t.get('need_val'),'monster':monster_name(t.get('cond_val') or td.get('_cur_kill_id_1')),'finished':t.get('fin'),
   'claimed':td.get('_got_reward'),'participants':members,'rewards':rewards(td.get('_rewardList'))})
 result={'role':{'name':clean(p.name),'short_id':p.short_id,'server_id':p.server_id},'tasks':rows,'available':True}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
