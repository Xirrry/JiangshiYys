"""Persist read-only weekly shop snapshots and chosen display items."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,re,time
import bounty_transport,role_reader,window_layout
TZ=timezone(timedelta(hours=8))
def is_cosmetic(g):
 name=g.get('name','');product=g.get('product',0)
 if '皮肤券' in name:return False
 return product==410206 or 450000<=product<460000 or bool(re.search('皮肤|配饰|面具|头像框|印染方案|折扇|聊天框|气泡',name))
class WeeklyShopStore:
 def __init__(self,root):self.root=Path(root);self.path=self.root/'data/weekly-shops.json'
 def load(self):
  if not self.path.exists():return {'roles':{},'visible':None}
  data=json.loads(self.path.read_text(encoding='utf-8'))
  roles=data.get('roles',{})
  for role in roles.values():role['goods']=[g for g in role.get('goods',[]) if not is_cosmetic(g)]
  return {'roles':roles,'visible':data.get('visible')}
 def write(self,data):
  self.path.parent.mkdir(parents=True,exist_ok=True)
  temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.path)
 def display(self,keys):
  if not isinstance(keys,list) or any(not isinstance(k,str) or not re.fullmatch(r'(?:[0-9]+|shrine_[0-9]+_[0-9]+|treasure_[0-9]+)',k) for k in keys):raise ValueError('商品选择无效')
  data=self.load();data['visible']=list(dict.fromkeys(keys));self.write(data);return data
 def windows(self,app):return [{'id':r['id'],'title':r['title']} for r in window_layout.running_game_windows(role_reader.game_pids(),app.process_stamp)]
 def save(self,doc):
  role=doc['role'];role_reader.parse_identity([[role['short_id'],role['server_id'],role['nickname'],1]],[])
  data=self.load();now=datetime.now(TZ);monday=now.date()-timedelta(days=now.weekday())
  servers=json.loads((self.root/'servers.json').read_text(encoding='utf-8'))['servers']
  role['server']=next((x['name'] for x in servers if str(x['id'])==str(role['server_id'])),'区服待识别')
  key=str(role['server_id'])+':'+str(role['short_id'])
  # Retain the last successful snapshot for offline roles.
  if 'queried_shops' in doc:
   previous=data['roles'].get(key,{})
   retained=[{**g,'stale':True} for g in previous.get('goods',[]) if g.get('shop') not in doc['queried_shops']]
   doc['goods']=[{**g,'stale':False} for g in doc['goods']]+retained
  data['roles'][key]={'key':key,'name':role['nickname'],'server':role['server'],'week':monday.isoformat(),'at':now.isoformat(timespec='seconds'),'goods':[g for g in doc['goods'] if not is_cosmetic(g)],'balances':doc.get('balances',{})}
  self.write(data)
  # Both the full shop page and weekly checklist reflect the latest successful read.
  import shop_checklist,task_checklist
  observations=shop_checklist.observations(data['roles'][key]['goods'],doc.get('balances',{}))
  if observations:task_checklist.ChecklistStore(self.root).save({'role':role,'observations':observations})
 def read(self,app,target='all'):
  rows=window_layout.running_game_windows(role_reader.game_pids(),app.process_stamp)
  if target!='all':rows=[x for x in rows if x['id']==target]
  if not rows:raise ValueError('没有可读取的窗口，请刷新窗口列表')
  results=[]
  def fetch(row):
   dll=self.root/'hardware/checklist-reader/checklist_agent.dll'
   request=None
   try:request=bounty_transport.read(row['pid'],int(row['stamp']),app.process_stamp,dll,16)
   except Exception:pass
   deadline=time.monotonic()+6
   while True:
    doc=bounty_transport.read(row['pid'],int(row['stamp']),app.process_stamp,dll,8)
    state=doc.pop('_shrine_query',{})
    same=bool(request and state.get('nonce')==request.get('nonce') and state.get('role')==request.get('role'))
    if same and state.get('ready') is True and state.get('treasure_ready') is True:break
    if not same or state.get('expired') or time.monotonic()>=deadline:
     invalid=[]
     if not (same and state.get('ready')):invalid.append('神龛')
     if not (same and state.get('treasure_ready')):invalid.append('千物宝库')
     doc['goods']=[g for g in doc['goods'] if g['shop'] not in invalid]
     doc['queried_shops']=[s for s in doc['queried_shops'] if s not in invalid]
     break
    time.sleep(.15)
   return doc
  for row,doc,error in bounty_transport.read_windows(rows,fetch):
   try:
    if error:raise error
    fresh_count=len(doc['goods']);self.save(doc);results.append({'title':row['title'],'count':fresh_count,'warning':'；'.join(name+'本次未获取到新响应，保留上次记录' for name in ('神龛','千物宝库') if name not in doc.get('queried_shops',[]))})
   except Exception as e:results.append({'title':row['title'],'error':str(e)})
  return {'snapshot':self.load(),'results':results}
