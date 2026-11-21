import sys,json
try:
 import Globals
 def clean(v,depth=0):
  if depth>7:return None
  if v is None or isinstance(v,(bool,int,float)):return v
  if isinstance(v,bytes):
   try:return v.decode('utf-8')
   except UnicodeError:return v.decode('gb18030','replace')
  if isinstance(v,str) or type(v).__name__ in ('unicode','long'):return v
  if isinstance(v,dict):return dict((clean(k,depth+1),clean(x,depth+1)) for k,x in list(v.items())[:100])
  if isinstance(v,(list,tuple)):return [clean(x,depth+1) for x in v[:100]]
  return None
 p=Globals.player1
 manager=sys.modules.get('ui.ShopManager')
 obj=getattr(manager,'_m_ins',None)
 m=sys.modules.get('ui.shop.NewSecretShopWidget')
 table=getattr(getattr(m,'SHOP_NEW_SECRET_SHOP',None),'data',{})
 info=getattr(p,'new_secret_shop_info',None)
 if not obj or not info or not table:raise ValueError('商店数据尚未加载，请先在游戏中打开神秘商店')
 shops=[]
 for idx in range(len(obj.receive_share_ids)+1):
  data=obj.get_shop_info_by_idx(idx)
  if not data:continue
  goods=[]
  for cell in data.get('cell_list',[]):
   row=table.get(cell)
   if row is None:continue
   rate=obj.getRareShopCoe(cell,idx)
   status,remain,flower=obj.check_can_buy_item(cell,idx)
   costs=[{'currency':v[0],'amount':max(1,int(v[1]*rate)),'original':v[1]} for v in row.get('Recipe',[])]
   product=row.get('ProductID',[0,0])
   goods.append({'key':str(cell),'name':clean(row.get('ProductName')),'quantity':product[1],
    'product':product[0],'costs':costs,'rate':rate,'special':bool(obj.check_is_cheap(cell,idx)),
    'flowers':int(row.get('intimat',0)),'remaining':remain if remain>=0 else None,
    'status':'sold' if status==-1 else 'locked' if status==-2 else 'available' if status==0 else 'unknown'})
  shops.append({'key':clean(data.get('inter_shop_id')),'own':idx==0,'index':idx,
   'level':obj.get_bought_history_level()[0] if idx==0 else data.get('shop_level'),
   'goods':goods})
 result={'role':{'name':clean(p.name),'short_id':p.short_id,'server_id':p.server_id},
  'flower_names':dict((str(i),clean(m.FriendData.getIntimacyLevelName(i))) for i in range(4)),
  'shops':shops,'seconds_left':obj.get_secret_shop_lefttime(),'shop_count':clean(obj.get_shop_count())}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
