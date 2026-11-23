"""Local per-character monitoring preferences and dated checklist observations."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3,json
from contextlib import contextmanager
TZ=timezone(timedelta(hours=8))
DAILY=['大神 · 每日福利','祈愿碎片','寮资金领取','商店 · 每日礼包','好友寄养','寮三十','地域鬼王','阴界之门','逢魔之时','首领退治','协战 50 次','悬赏封印','金币妖怪','经验妖怪']
WEEKLY=['大神 · 3天福利','大神 · 5天福利','大神 · 7天福利','大神 · 100天福利','大神 · 200天福利','秘闻','图鉴分享','秘闻分享','地域鬼王分享','勋章商店','寮商店','荣誉商店','神龛','御灵境之钥','鼠乐园 · 礼盒兑换','六道之门 · 万相赐福','契灵','永生之海 · 奖励翻倍','真蛇','斗技 · 每周5胜','斗技 · 每周荣誉']
CATALOG=[{'id':prefix+str(i),'name':name,'period':period,'lifetime':name in ('大神 · 100天福利','大神 · 200天福利')} for period,prefix,names in [('daily','d',DAILY),('weekly','w',WEEKLY)] for i,name in enumerate(names)]
SUPPORTED={'w6','w7','w5','w8','d0','d1','d2','d3','d4','d5','d6','d8','d9','d10','w0','w1','w2','w3','w4'}
# Keep persisted task identifiers stable; old bounty observations remain on disk.
CATALOG=[task for task in CATALOG if task['id'] not in ('d11','w9','w10','w11','w12','w13','w14','w16')]
for task in CATALOG:
 if task['id'] in ('d5','d7','d9'):task['category']='guild'
 if task['id']=='d8':task['name']='现世逢魔 · 4次'
 if task['id']=='d9':task['period']='weekly'
 if task['id']=='d4':task['monitor']=True
CATALOG.append({'id':'realm_card','name':'自己的结界卡','period':'daily','lifetime':False,'monitor':True})
CATALOG.append({'id':'evening_boss','name':'逢魔 Boss · 战斗进度','period':'daily','lifetime':False})
SUPPORTED.update(('evening_boss','d7','d12','d13'))
CATALOG.append({'id':'pact_shop_souls','name':'契灵商店 · 100御魂兑换','category':'shop','period':'weekly','lifetime':False})
SUPPORTED.update(('realm_card','w15','w17','w18','w19','w20','pact_shop_souls'))
from shop_checklist import TASKS as SHOP_TASKS
CATALOG.extend(SHOP_TASKS)
SUPPORTED.update(t['id'] for t in SHOP_TASKS)
CATALOG.append({'id':'mentoring_practice','name':'守护历练 · 每日5次','period':'daily','lifetime':False,'category':'mentoring'})
CATALOG.append({'id':'mentoring_recruit','name':'收徒冷却','period':'daily','lifetime':False,'monitor':True,'category':'mentoring'})
CATALOG.append({'id':'mentoring_points','name':'师徒历练点数','period':'daily','lifetime':False,'monitor':True,'category':'mentoring'})
SUPPORTED.update(('mentoring_practice','mentoring_recruit','mentoring_points'))
CATALOG.extend([{'id':'guild_banquet','name':'阴阳寮宴会 · 每周2次','period':'weekly','lifetime':False,'category':'guild'},{'id':'guild_kirin','name':'麒麟 · 狩猎战','period':'daily','lifetime':False,'category':'guild'}])
SUPPORTED.update(('guild_banquet','guild_kirin'))
CATALOG.append({'id':'lanqi_exchange','name':'兰契 · 碎片交换冷却','period':'daily','lifetime':False,'monitor':True})
SUPPORTED.add('lanqi_exchange')
IDS={x['id'] for x in CATALOG}
def bucket(period,now=None,hour=0):
 now=now or datetime.now(TZ)
 day=(now.astimezone(TZ)-timedelta(hours=hour)).date()
 return (day-timedelta(days=day.weekday()) if period=='weekly' else day).isoformat()
def running_role_window(app,role_key,root):
 import bounty_transport,role_reader,window_layout
 if not isinstance(role_key,str) or not role_key.count(':')==1:raise ValueError('角色选择无效')
 rows=window_layout.running_game_windows(role_reader.game_pids(),app.process_stamp)
 for row in rows:
  try:
   doc=bounty_transport.read(row['pid'],int(row['stamp']),app.process_stamp,Path(root)/'hardware/checklist-reader/checklist_agent.dll',32)
   identity=doc.get('role',{})
   key=str(identity.get('server_id'))+':'+str(identity.get('short_id'))
   if key==role_key:return row
  except Exception:continue
 raise ValueError('未找到该角色的运行窗口，请确认角色已登录；原记录已保留')

class ChecklistStore:
 def __init__(self,root):
  self.path=Path(root)/'data/task-checklist.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS task_setting_snapshots(id TEXT PRIMARY KEY,name TEXT UNIQUE,payload TEXT,source TEXT,at TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_groups(id TEXT PRIMARY KEY,name TEXT,collapsed INTEGER DEFAULT 0)')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_members(role TEXT PRIMARY KEY,group_id TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_ui(key TEXT PRIMARY KEY,value INTEGER)')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_hidden_roles(role TEXT PRIMARY KEY)')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_role_order(role TEXT PRIMARY KEY,position INTEGER NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS last_week_storage(role TEXT,task TEXT,week TEXT,saved INTEGER,received INTEGER,at TEXT,PRIMARY KEY(role,task,week))')
   db.execute('CREATE TABLE IF NOT EXISTS checklist_task_defaults(task TEXT PRIMARY KEY,priority TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS task_priorities(role TEXT,task TEXT,priority TEXT,PRIMARY KEY(role,task))')
   db.execute('CREATE TABLE IF NOT EXISTS mentoring_cooldown(role TEXT PRIMARY KEY,payload TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS lanqi_monitor(role TEXT PRIMARY KEY,end REAL NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS realm_card_monitor(role TEXT PRIMARY KEY,start REAL,end REAL,label TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS foster_monitor(role TEXT PRIMARY KEY,start REAL,end REAL,target TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS task_parts(role TEXT,task TEXT,bucket TEXT,payload TEXT,PRIMARY KEY(role,task,bucket))')
   db.execute('CREATE TABLE IF NOT EXISTS detections(role TEXT PRIMARY KEY,at TEXT)')
   db.executescript('CREATE TABLE IF NOT EXISTS roles(key TEXT PRIMARY KEY,payload TEXT);CREATE TABLE IF NOT EXISTS prefs(role TEXT,task TEXT,enabled INTEGER,PRIMARY KEY(role,task));CREATE TABLE IF NOT EXISTS observations(role TEXT,task TEXT,bucket TEXT,status TEXT,source TEXT,detail TEXT,at TEXT,PRIMARY KEY(role,task,bucket));')
   db.execute("UPDATE observations SET status='active',detail='已发起祈愿，碎片到账尚待核实' WHERE task='d1' AND source='auto' AND status='done' AND detail='已发起碎片祈愿'")
 @contextmanager
 def connect(self):
  db=sqlite3.connect(self.path,timeout=10)
  try:
   with db:yield db
  finally:db.close()
 def register(self,roles):
  with self.connect() as db:
   for r in roles:
    if not r.get('short_id') or not r.get('server_id'):continue
    role={'key':str(r['server_id'])+':'+str(r['short_id']),'name':r.get('nickname') or r.get('name') or '未命名角色','server':r.get('server','')}
    db.execute('INSERT OR REPLACE INTO roles VALUES(?,?)',(role['key'],json.dumps(role,ensure_ascii=False)))
 def load(self):
  with self.connect() as db:
   roles=[json.loads(r[0]) for r in db.execute("SELECT payload FROM roles WHERE key IN (SELECT role FROM detections UNION SELECT role FROM observations WHERE source='auto') ORDER BY key")]
   hidden={row[0] for row in db.execute('SELECT role FROM checklist_hidden_roles')}
   archived_roles=[role for role in roles if role['key'] in hidden]
   roles=[role for role in roles if role['key'] not in hidden]
   snapshots=[]
   role_order=dict(db.execute('SELECT role,position FROM checklist_role_order'))
   roles.sort(key=lambda row:(role_order.get(row['key'],10**9),row['key']))
   for key,name,payload,source,at in db.execute('SELECT id,name,payload,source,at FROM task_setting_snapshots ORDER BY at DESC,rowid DESC'):
    saved=json.loads(payload);values=list(saved['tasks'].values());snapshots.append({'id':key,'name':name,'scope':saved['scope'],'source':source,'at':at,'count':len(values),'enabled':sum(bool(v['enabled']) for v in values),'important':sum(v['priority']=='important' for v in values),'muted':sum(v['priority']=='muted' for v in values)})
   groups=[{'id':g[0],'name':g[1],'collapsed':bool(g[2])} for g in db.execute('SELECT id,name,collapsed FROM checklist_groups ORDER BY rowid')]
   default=db.execute("SELECT value FROM checklist_ui WHERE key='ungrouped_collapsed'").fetchone()
   groups.append({'id':'','name':'未分组','collapsed':bool(default and default[0])})
   members=dict(db.execute('SELECT role,group_id FROM checklist_members'))
   defaults=dict(db.execute('SELECT task,priority FROM checklist_task_defaults'))
   for role in roles:
    role['group_id']=members.get(role['key'],'')
    prefs=dict(db.execute('SELECT task,enabled FROM prefs WHERE role=?',(role['key'],)))
    priorities=dict(db.execute('SELECT task,priority FROM task_priorities WHERE role=?',(role['key'],)))
    role['tasks']=[]
    for t in CATALOG:
     b='monitor' if t.get('monitor') else 'lifetime' if t['lifetime'] else bucket(t['period'])
     row=db.execute('SELECT status,source,detail,at FROM observations WHERE role=? AND task=? AND bucket=?',(role['key'],t['id'],b)).fetchone()
     parts=db.execute('SELECT payload FROM task_parts WHERE role=? AND task=? AND bucket=?',(role['key'],t['id'],b)).fetchone()
     foster=db.execute('SELECT start,end,target FROM foster_monitor WHERE role=?',(role['key'],)).fetchone() if t['id']=='d4' else None
     role['tasks'].append({**t,'priority':priorities.get(t['id'],defaults.get(t['id'],'normal')),'enabled':bool(prefs.get(t['id'],1)),'status':row[0] if row else 'unknown','source':row[1] if row else '', 'parts':json.loads(parts[0]) if parts and row and row[1]=='auto' else [],'support':t['id'] in SUPPORTED,'detail':row[2] if row else ('当前周期暂无有效数据' if t['id'] in SUPPORTED else '尚未接入自动检测'),'at':row[3] if row else ''})
     role['tasks'][-1]['available']=datetime.now(TZ).weekday() in ({'d7':(4,5,6),'guild_kirin':(0,1,2,3)}.get(t['id'],range(7)))
     if not role['tasks'][-1]['available']:
      role['tasks'][-1].update(status='unavailable',detail=('周一至周四开放' if t['id']=='guild_kirin' else '周五至周日开放')+' · 今日未开放')
     elif t['id']=='guild_kirin' and not row:role['tasks'][-1]['detail']='周一至周四开放 · 当前周期暂无有效个人数据'
     stored=db.execute('SELECT saved,received,at FROM last_week_storage WHERE role=? AND task=? AND week=?',(role['key'],t['id'],bucket('weekly'))).fetchone()
     if stored:role['tasks'][-1]['storage']={'saved':stored[0],'received':stored[1],'remaining':stored[0]-stored[1],'week':bucket('weekly'),'at':stored[2]}
     if t['id']=='d4' and foster and row and row[1]=='auto':
      task=role['tasks'][-1];remaining=max(0,int(foster[1]-datetime.now(TZ).timestamp()))
      task['ends_at']=foster[1];task['target_name']=foster[2]
      task['status']='fostering' if remaining>0 else 'home'
      if remaining>0:task['detail']='寄养中 · '+foster[2]+' · 剩余 '+str(remaining//3600)+'小时'+str((remaining%3600)//60)+'分 · '+datetime.fromtimestamp(foster[1],TZ).strftime('%H:%M')+' 到期'
      else:task['detail']=('寄养回家了，记得再次寄养 · '+foster[2]) if foster[1]>0 else '当前没有寄养，记得安排寄养'
     if t['id']=='lanqi_exchange' and row and row[1]=='auto':
      cooldown=db.execute('SELECT end FROM lanqi_monitor WHERE role=?',(role['key'],)).fetchone()
      if cooldown:
       end=cooldown[0];now=datetime.now(TZ).timestamp();task=role['tasks'][-1]
       task.update(ends_at=end,status='cooldown' if end>now else 'ready')
       if end>now:
        left=max(0,int(end-now));hours,seconds=divmod(left,3600);minutes=seconds//60
        task['detail']='剩余 '+str(hours)+'小时'+str(minutes)+'分 · '+datetime.fromtimestamp(end,TZ).strftime('%m/%d %H:%M')+' 可交换'
       else:task['detail']='碎片交换冷却已结束，可以再次交换'
     if t['id']=='mentoring_recruit' and row and row[1]=='auto':
      record=db.execute('SELECT payload FROM mentoring_cooldown WHERE role=?',(role['key'],)).fetchone()
      if record:
       task=role['tasks'][-1];meta=json.loads(record[0]);end=meta['end'];remaining=max(0,int(end-datetime.now(TZ).timestamp()));occupied=meta['occupied']
       task['ends_at']=end
       task['status']='cooldown' if remaining else 'occupied' if occupied else 'ready' if meta['start'] else 'inactive'
       if remaining:
        duration=str(remaining//86400)+'天'+str(remaining%86400//3600)+'小时'+str(remaining%3600//60)+'分'
        task['detail']='距收徒冷却结束 '+duration+' · '+datetime.fromtimestamp(end,TZ).strftime('%m-%d %H:%M')+' 到期'+(' · 当前已有徒弟，出师后才腾出空位' if occupied else ' · 当前空位已腾出')
       elif occupied:task['detail']='96小时冷却已结束 · 当前已有徒弟，仍需出师后才能再次收徒'
       elif meta['start']:task['detail']='96小时冷却已结束 · 当前无徒弟，收徒资格以游戏为准'
       else:task['detail']='暂无收徒冷却记录'+(' · 当前为后辈' if meta.get('relation_state')==2 else '')
     if t['id']=='realm_card' and row and row[1]=='auto':
      card=db.execute('SELECT start,end,label FROM realm_card_monitor WHERE role=?',(role['key'],)).fetchone()
      if card:
       task=role['tasks'][-1];remaining=max(0,int(card[1]-datetime.now(TZ).timestamp()))
       task.update(ends_at=card[1],card_name=card[2],status='card_running' if remaining>0 else 'card_expired')
       task['detail']=(card[2]+' · 剩余 '+str(remaining//3600)+'小时'+str((remaining%3600)//60)+'分 · '+datetime.fromtimestamp(card[1],TZ).strftime('%m-%d %H:%M')+' 到期') if remaining>0 else ('结界卡已到期，记得换卡 · '+card[2] if card[1]>0 else '当前没有使用结界卡，记得配置')
  return {'roles':roles,'archived_roles':archived_roles,'groups':groups,'snapshots':snapshots,'catalog':CATALOG,'day':bucket('daily'),'week':bucket('weekly')}
 def setting_snapshot(self,p):
  import uuid
  action=p.get('action');key=p.get('id')
  with self.connect() as db:
   if action=='save':
    name=p.get('name','');scope=p.get('scope','all');role=p.get('role')
    if not isinstance(name,str) or not 1<=len(name.strip())<=40:raise ValueError('快照名称需为1至40字')
    name=name.strip()
    if scope not in ('all','daily','weekly'):raise ValueError('保存范围无效')
    row=db.execute('SELECT payload FROM roles WHERE key=?',(role,)).fetchone()
    if not row:raise ValueError('来源角色不存在')
    if key and not db.execute('SELECT 1 FROM task_setting_snapshots WHERE id=?',(key,)).fetchone():raise ValueError('快照不存在，请刷新后重试')
    if db.execute('SELECT 1 FROM task_setting_snapshots WHERE name=? AND id!=?',(name,key or '')).fetchone():raise ValueError('快照名称已存在，请使用其他名称或更新所选快照')
    enabled=dict(db.execute('SELECT task,enabled FROM prefs WHERE role=?',(role,)))
    priority=dict(db.execute('SELECT task,priority FROM task_priorities WHERE role=?',(role,)))
    defaults=dict(db.execute('SELECT task,priority FROM checklist_task_defaults'))
    tasks={t['id']:{'enabled':bool(enabled.get(t['id'],1)),'priority':priority.get(t['id'],defaults.get(t['id'],'normal'))} for t in CATALOG if scope=='all' or t['period']==scope}
    saved={'version':1,'scope':scope,'tasks':tasks};key=key or uuid.uuid4().hex
    db.execute('INSERT OR REPLACE INTO task_setting_snapshots VALUES(?,?,?,?,?)',(key,name,json.dumps(saved,ensure_ascii=False),json.loads(row[0])['name'],datetime.now(TZ).isoformat(timespec='seconds')))
    return {'snapshot_id':key,'count':len(tasks)}
   row=db.execute('SELECT payload FROM task_setting_snapshots WHERE id=?',(key,)).fetchone()
   if not row:raise ValueError('快照不存在，请刷新后重试')
   if action=='remove':db.execute('DELETE FROM task_setting_snapshots WHERE id=?',(key,));return {'removed':key}
   if action!='apply':raise ValueError('快照操作无效')
   roles=p.get('roles')
   if not isinstance(roles,list) or not roles or any(not isinstance(x,str) for x in roles):raise ValueError('请至少选择一个目标角色')
   roles=list(dict.fromkeys(roles));known={row[0] for row in db.execute('SELECT key FROM roles')}
   if any(role not in known for role in roles):raise ValueError('目标角色已变化，请刷新后重新选择')
   saved=json.loads(row[0]);tasks={task:v for task,v in saved['tasks'].items() if task in IDS}
   if not tasks:raise ValueError('快照中没有当前版本支持的任务')
   for task,v in tasks.items():
    if type(v.get('enabled')) is not bool or v.get('priority') not in ('normal','important','muted'):raise ValueError('快照配置无效，未应用')
   for role in roles:
    for task,v in tasks.items():
     db.execute('INSERT OR REPLACE INTO prefs VALUES(?,?,?)',(role,task,int(v['enabled'])))
     db.execute('INSERT OR REPLACE INTO task_priorities VALUES(?,?,?)',(role,task,v['priority']))
   return {'applied':len(roles),'count':len(tasks),'snapshot_id':key}
 def default_muted_from_role(self,role):
  with self.connect() as db:
   if not db.execute('SELECT 1 FROM roles WHERE key=?',(role,)).fetchone():raise ValueError('模板角色不存在')
   tasks=[row[0] for row in db.execute("SELECT task FROM task_priorities WHERE role=? AND priority='muted'",(role,)) if row[0] in IDS]
   if not tasks:raise ValueError('模板角色没有设为不提醒的任务，未更改其他角色')
   db.execute('DELETE FROM checklist_task_defaults')
   for task in tasks:
    db.execute("INSERT INTO checklist_task_defaults VALUES(?,'muted')",(task,))
    db.execute("INSERT OR REPLACE INTO task_priorities(role,task,priority) SELECT key,?,'muted' FROM roles",(task,))
  return tasks
 def group(self,p):
  import uuid
  action=p.get('action');group=p.get('id','')
  with self.connect() as db:
   def exists():
    if not group or not db.execute('SELECT 1 FROM checklist_groups WHERE id=?',(group,)).fetchone():raise ValueError('分组不存在')
   if action in ('hide_role','restore_role'):
    role=p.get('role')
    if not isinstance(role,str) or not db.execute('SELECT 1 FROM roles WHERE key=?',(role,)).fetchone():raise ValueError('角色档案不存在')
    if action=='hide_role':db.execute('INSERT OR IGNORE INTO checklist_hidden_roles VALUES(?)',(role,))
    else:db.execute('DELETE FROM checklist_hidden_roles WHERE role=?',(role,))
   elif action=='reorder':
    order=p.get('roles')
    known={row[0] for row in db.execute("SELECT key FROM roles WHERE key NOT IN (SELECT role FROM checklist_hidden_roles) AND key IN (SELECT role FROM detections UNION SELECT role FROM observations WHERE source='auto')")}
    if not isinstance(order,list) or not all(isinstance(key,str) for key in order) or len(order)!=len(set(order)) or set(order)!=known:raise ValueError('角色列表已变化，请刷新后重新排序')
    db.executemany('INSERT OR REPLACE INTO checklist_role_order VALUES(?,?)',[(key,index) for index,key in enumerate(order)])
   elif action in ('create','rename'):
    name=p.get('name','')
    if not isinstance(name,str) or not name.strip() or len(name.strip())>30 or name.strip()=='未分组':raise ValueError('请输入1至30字的分组名称')
    name=name.strip()
    if db.execute('SELECT 1 FROM checklist_groups WHERE name=? AND id!=?',(name,group if action=='rename' else '')).fetchone():raise ValueError('分组名称已存在')
    if action=='create':db.execute('INSERT INTO checklist_groups(id,name) VALUES(?,?)',(uuid.uuid4().hex,name))
    else:exists();db.execute('UPDATE checklist_groups SET name=? WHERE id=?',(name,group))
   elif action=='assign':
    if group:exists()
    role=p.get('role')
    if not db.execute('SELECT 1 FROM roles WHERE key=?',(role,)).fetchone():raise ValueError('角色不存在')
    db.execute('INSERT OR REPLACE INTO checklist_members VALUES(?,?)',(role,group))
   elif action=='remove':
    exists();db.execute("UPDATE checklist_members SET group_id='' WHERE group_id=?",(group,));db.execute('DELETE FROM checklist_groups WHERE id=?',(group,))
   elif action in ('toggle','collapse_all'):
    collapsed=p.get('collapsed')
    if type(collapsed) is not bool:raise ValueError('折叠状态无效')
    if action=='collapse_all':db.execute('UPDATE checklist_groups SET collapsed=?',(int(collapsed),))
    elif group:exists();db.execute('UPDATE checklist_groups SET collapsed=? WHERE id=?',(int(collapsed),group))
    if action=='collapse_all' or not group:db.execute("INSERT OR REPLACE INTO checklist_ui VALUES('ungrouped_collapsed',?)",(int(collapsed),))
   else:raise ValueError('分组操作无效')
 def set(self,p):
  role=p['role'];task=p['task']
  if task not in IDS:raise ValueError('任务无效')
  with self.connect() as db:
   if not db.execute('SELECT 1 FROM roles WHERE key=?',(role,)).fetchone():raise ValueError('角色不存在')
   if 'priority' in p:
    if p['priority'] not in ('important','normal','muted'):raise ValueError('重要程度无效')
    if not db.execute('SELECT 1 FROM roles WHERE key=?',(role,)).fetchone():raise ValueError('角色不存在')
    db.execute('INSERT OR REPLACE INTO task_priorities VALUES(?,?,?)',(role,task,p['priority']))
   elif 'enabled' in p:
    if type(p['enabled']) is not bool:raise ValueError('监控设置无效')
    db.execute('INSERT OR REPLACE INTO prefs VALUES(?,?,?)',(role,task,int(p['enabled'])))
   else:
    if task in ('d4','realm_card','mentoring_recruit','mentoring_points','lanqi_exchange'):raise ValueError('计时监控不需要勾选完成')
    if p.get('status') not in ('unknown','todo','done','claimable','active'):raise ValueError('状态无效')
    t=next(x for x in CATALOG if x['id']==task);b='monitor' if t.get('monitor') else 'lifetime' if t['lifetime'] else bucket(t['period'])
    db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?)',(role,task,b,p['status'],'manual','手动确认',datetime.now(TZ).isoformat(timespec='seconds')))
 def save(self,document):
  r=document['role'];self.register([r]);key=str(r['server_id'])+':'+str(r['short_id'])
  with self.connect() as db:
   db.execute('INSERT OR REPLACE INTO detections VALUES(?,?)',(key,datetime.now(TZ).isoformat(timespec='seconds')))
   stored=document.get('_last_week_storage',{})
   if isinstance(stored,dict):
    for task,value in stored.items():
     if task not in ('w18','guild_banquet','d9','d7') or not isinstance(value,dict):continue
     saved=value.get('saved');received=value.get('received')
     if type(saved) is int and type(received) is int and 0<=received<=saved<=10:db.execute('INSERT OR REPLACE INTO last_week_storage VALUES(?,?,?,?,?,?)',(key,task,bucket('weekly'),saved,received,datetime.now(TZ).isoformat(timespec='seconds')))
   for task,value in document.get('observations',{}).items():
    if task not in IDS or value.get('status') not in ('todo','done','claimable','active','fostering','home','card_running','card_expired','cooldown','occupied','ready','inactive','progressing','target_met'):continue
    t=next(x for x in CATALOG if x['id']==task);b='monitor' if t.get('monitor') else 'lifetime' if t['lifetime'] else bucket(t['period'])
    if task=='lanqi_exchange':
     end=value.get('exchange_end')
     if type(end) not in (int,float) or not 0<=end<10**11:continue
     db.execute('INSERT OR REPLACE INTO lanqi_monitor VALUES(?,?)',(key,end))
    if task=='mentoring_recruit':
     meta=value.get('mentoring',{})
     if not isinstance(meta,dict) or type(meta.get('start')) not in (int,float) or type(meta.get('end')) not in (int,float) or not 0<=meta['start']<=meta['end']<10**11 or type(meta.get('occupied')) is not bool:continue
     if meta['start'] and meta['end']-meta['start']!=96*3600:continue
     db.execute('INSERT OR REPLACE INTO mentoring_cooldown VALUES(?,?)',(key,json.dumps(meta,ensure_ascii=False)))
    if task=='d4':
     meta=value.get('foster',{})
     if not isinstance(meta,dict) or type(meta.get('end')) not in (int,float) or not 0<=meta['end']<10**11:continue
     if meta['end']==0:
      prior=db.execute('SELECT start,end,target FROM foster_monitor WHERE role=?',(key,)).fetchone()
      if prior and 0<prior[1]<=datetime.now(TZ).timestamp():meta={'start':prior[0],'end':prior[1],'target':prior[2]}
     db.execute('INSERT OR REPLACE INTO foster_monitor VALUES(?,?,?,?)',(key,meta.get('start',0),meta['end'],str(meta.get('target') or '好友结界')))
    if task=='realm_card':
     meta=value.get('realm_card',{})
     if not isinstance(meta,dict) or type(meta.get('end')) not in (int,float) or not 0<=meta['end']<10**11:continue
     if meta['end']==0:
      prior=db.execute('SELECT start,end,label FROM realm_card_monitor WHERE role=?',(key,)).fetchone()
      if prior and 0<prior[1]<=datetime.now(TZ).timestamp():meta={'start':prior[0],'end':prior[1],'label':prior[2]}
     db.execute('INSERT OR REPLACE INTO realm_card_monitor VALUES(?,?,?,?)',(key,meta.get('start',0),meta['end'],str(meta.get('label') or '结界卡')))
    detail=str(value.get('detail',''))
    if task=='d2' and value['status']=='done' and detail=='今日已领取，金额未读到':
     prior=db.execute('SELECT detail FROM observations WHERE role=? AND task=? AND bucket=? AND source=? AND status=?',(key,task,b,'auto','done')).fetchone()
     if prior and prior[0].startswith('今日已领取资金 '):detail=prior[0]
    db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?)',(key,task,b,value['status'],'auto',detail,datetime.now(TZ).isoformat(timespec='seconds')))

    if task=='d1' and isinstance(value.get('parts'),list):
     parts=[{k:v for k,v in part.items() if k in ('name','status','detail','current','target','hero_name')} for part in value['parts'] if isinstance(part,dict) and part.get('name') in ('寮祈愿','好友祈愿') and part.get('status') in ('unknown','todo','active','done')]
     db.execute('INSERT OR REPLACE INTO task_parts VALUES(?,?,?,?)',(key,task,b,json.dumps(parts,ensure_ascii=False)))

 def foster_reminders(self):
  with self.connect() as db:
   rows=db.execute("SELECT roles.payload,f.end,f.target FROM foster_monitor f JOIN roles ON roles.key=f.role LEFT JOIN prefs p ON p.role=f.role AND p.task='d4' LEFT JOIN task_priorities i ON i.role=f.role AND i.task='d4' WHERE roles.key NOT IN (SELECT role FROM checklist_hidden_roles) AND f.end>0 AND f.end<=? AND COALESCE(p.enabled,1)=1 AND COALESCE(i.priority,'normal')!='muted'",(datetime.now(TZ).timestamp(),)).fetchall()
   cards=db.execute("SELECT roles.payload,c.end,c.label FROM realm_card_monitor c JOIN roles ON roles.key=c.role LEFT JOIN prefs p ON p.role=c.role AND p.task='realm_card' LEFT JOIN task_priorities i ON i.role=c.role AND i.task='realm_card' WHERE roles.key NOT IN (SELECT role FROM checklist_hidden_roles) AND c.end>0 AND c.end<=? AND COALESCE(p.enabled,1)=1 AND COALESCE(i.priority,'normal')!='muted'",(datetime.now(TZ).timestamp(),)).fetchall()
  return [{**json.loads(role),'kind':'foster','ends_at':end,'target':target} for role,end,target in rows]+[{**json.loads(role),'kind':'realm_card','ends_at':end,'target':label} for role,end,label in cards]
