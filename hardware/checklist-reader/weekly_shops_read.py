import json,sys,re
try:
 import Globals
 p=Globals.player1
 mod=sys.modules.get('ui.ShopManager')
 if mod is None:mod=__import__('ui.ShopManager',fromlist=['ShopManager'])
 manager=mod.ShopManager.getInstance()
 table=getattr(getattr(sys.modules.get('DynamicConfigData'),'DATA_SHOP',None),'data',{})
 method=getattr(manager.getNormalShopItemRemainNum,'__func__',manager.getNormalShopItemRemainNum)
 helpers=getattr(method,'__globals__',{}).get('helpers')
 def currency_name(cid):
  try:return helpers.getCurrencyName(cid) or ''
  except Exception:return ''
 currency_table=getattr(getattr(sys.modules.get('DynamicConfigData'),'DATA_CURRENCY',None),'data',{})
 def cosmetic(product,name):
  if '皮肤券' in name:return False
  row=currency_table.get(product,{})
  return row.get('type') in (41,905) or bool(re.search('皮肤|配饰|面具|头像框|印染方案|折扇|聊天框|气泡',name))
 goods=[]
 groups={1:'特殊商店',7:'斗技赛年商店',3:'友情商店',300:'御魂礼盒',2:'荣誉商店',4:'勋章商店',700:'寮商店',1400:'寄售屋',2500:'鼬乐园'}
 import datetime
 now=datetime.datetime.utcnow()+datetime.timedelta(hours=8)
 def currently_listed(row):
  for key in ('begin_time','end_time'):
   raw=row.get(key)
   if raw:
    if not isinstance(raw,(list,tuple)) or len(raw)<5:return False
    try:stamp=datetime.datetime(*(list(raw[:6])+([0] if len(raw)==5 else [])))
    except Exception:return False
    if key=='begin_time' and now<stamp:return False
    if key=='end_time' and now>stamp:return False
  return True
 for cid,row in table.items():
  if not hasattr(row,'get'):continue
  limits=row.get('limit',[]);shop=row.get('ShopID')
  if not isinstance(limits,(list,tuple)) or len(limits)<2 or type(limits[1]) is not int or limits[1]<=0:continue
  if shop not in (1,2,7) and limits[0]!=5:continue
  if not currently_listed(row):continue
  if shop not in groups and cid not in (10,200):continue
  if shop==700 and len(limits)>2:continue
  try:
   remaining=manager.getNormalShopItemRemainNum(cid)
   bought=manager.getThisWeekBuyNum(cid) if limits[0]==5 else limits[1]-remaining
   if type(bought) not in (int,float) or type(remaining) not in (int,float) or bought<0 or remaining<0:continue
   product=row.get('ProductID',[])
   if len(product)!=2 or cosmetic(product[0],row.get('ProductName','')):continue
   costs=[{'id':int(x[0]),'amount':x[1],'name':currency_name(int(x[0]))} for x in row.get('Recipe',[]) if isinstance(x,(list,tuple)) and len(x)==2]
   label='御灵境之钥' if cid==10 else '六道之门' if cid==200 else groups.get(shop,'特殊商店')
   currencies=[x['id'] for x in costs]
   if shop==2 and 900507 in currencies:label='斗技名士商店'
   elif shop==2 and 9491001 in currencies:label='斗技赛事商店'
   cycle='weekly' if limits[0]==5 else 'daily' if limits[0]==4 else 'limited'
   limit_label='每周' if cycle=='weekly' else '每日' if cycle=='daily' else '活动' if row.get('end_time') else '累计'
   requirements=[]
   if row.get('master'):requirements.append('名士限定' if row['master']>=10 else '斗技段位限定')
   if row.get('pvp_year_coin_req'):requirements.append('需累计赛年荣誉 '+format(row['pvp_year_coin_req'],','))
   if len(limits)>=3 and type(limits[2]) is int and limits[2]>0:requirements.append('角色等级 '+str(limits[2])+' 级')
   goods.append({'key':str(cid),'shop':label,'name':('三星' if product[0]==940000 and '星' not in row.get('ProductName','') else '')+row.get('ProductName','未命名商品'),'product':int(product[0]),'quantity':product[1],'bought':int(bought),'limit':int(bought+remaining),'remaining':int(remaining),'costs':costs,'cost_text':row.get('RecipeDesc',''),'cycle':cycle,'limit_label':limit_label,'requirements':requirements})
  except Exception:pass
 query=getattr(Globals,'_yys_weekly_shrine_query',{})
 query_meta={k:query.get(k) for k in ('nonce','role','ready','expired','treasure_ready')}
 queried=list(groups.values())+['御灵境之钥','六道之门','斗技名士商店','斗技赛事商店']
 if query.get('role')==str(p.server_id)+':'+str(p.short_id) and query.get('ready') and not query.get('expired'):
  defs=getattr(sys.modules.get('com.param_def'),'ParamNameDef',None)
  record=p.entity_get_param(defs.LIMIT_HUNYU) if defs else None
  table2=getattr(getattr(sys.modules.get('DynamicConfigData'),'DATA_HERO_SHOP',None),'data',{})
  if hasattr(record,'get'):
   matched=record.get('buy_item')==query['kind'] and record.get('buy_time')==query['begin']
   for cid,row in table2.items():
    if row.get('item_type')!=query['kind'] or row.get('goodType') not in (1,5,7):continue
    limit=row.get('limit');product=row.get('goodId');star=row.get('star',0)
    if cosmetic(product,row.get('name','')):continue
    if type(limit) is not int or limit<=0 or type(product) is not int:continue
    bought=record.get(str(cid),record.get(cid,0)) if matched else 0
    if type(bought) is not int or not 0<=bought<=limit:continue
    goods.append({'key':'shrine_'+str(product)+'_'+str(star),'shop':'神龛','name':row.get('name','神龛商品'),'product':product,'quantity':1,'bought':bought,'limit':limit,'remaining':limit-bought,'cycle':'period','period_start':query['begin'],'costs':[{'id':int(x[0]),'amount':x[1],'name':currency_name(int(x[0]))} for x in row.get('cost',[]) if len(x)==2]})
   queried.append('神龛')
 if query.get('role')==str(p.server_id)+':'+str(p.short_id) and query.get('treasure_ready') and not query.get('expired'):
  try:
   aes=__import__('com.activity.ActivityEventSystem',fromlist=['ActivityEventSystem']).ActivityEventSystem.instance()
   act=aes._get_activity_by_shop_id(7483);comp=act.get_comp('ShopComp') if act else None
   rows=comp.get_shop_data() if comp else None
   if isinstance(rows,(list,tuple)):
    for row in rows:
     if row.get('shopId')!=2:continue
     limit=row.get('weeklimit');left=row.get('left_num');product=row.get('currency_id');name=row.get('name','')
     if cosmetic(product,name):continue
     if type(limit) is not int or limit<=0 or type(left) is not int or not 0<=left<=limit:continue
     goods.append({'key':'treasure_'+str(row['id']),'shop':'千物宝库','name':name,'product':product,'quantity':row.get('num',1),'bought':limit-left,'limit':limit,'remaining':left,'cycle':'weekly','limit_label':'每周','costs':[{'id':x[0],'amount':x[1],'name':currency_name(x[0])} for x in row.get('formula',[]) if len(x)==2],'requirements':[]})
    queried.append('千物宝库')
  except Exception:pass
 balances={}
 for cid in set(c['id'] for g in goods for c in g['costs']):
  try:
   amount=p.getCurrency(cid)
   if type(amount) in (int,float) and amount>=0:balances[str(cid)]={'id':cid,'name':currency_name(cid),'amount':amount}
  except Exception:pass
 if not goods:raise ValueError('尚未取得有效的商店数据')
 result={'role':{'nickname':p.name,'short_id':p.short_id,'server_id':p.server_id},'goods':goods,'balances':balances,'queried_shops':queried,'_shrine_query':query_meta}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
