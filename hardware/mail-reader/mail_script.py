import json,sys
try:
 m=sys.modules['com.MailData'];rows=[];soul_names={}
 def clean(v):
  if type(v) in (list,tuple):return [clean(x) for x in v]
  if type(v) in (int,str,float,bool) or v is None:return v
  if type(v).__name__ in ('long','unicode'):return v
  return None
 mails=m.__dict__.get('mailDataList',[])
 if len(mails)>10000:raise ValueError('Too many loaded mails; nothing truncated or saved')
 for mail in mails:
  d=mail if type(mail) is dict else object.__getattribute__(mail,'__dict__')
  t=d.get('type');reason=d.get('reason','')
  xiajian=(t==622502 and reason=='gc_receive_settle_reward_boss') or (t==622503 and reason=='gc_receive_settle_reward_position')
  if t==400175 or not (str(reason).startswith(('gym','dojo')) or t==400179 or xiajian):continue
  raw=d.get('items')
  if type(raw) not in (list,tuple) or len(raw)>10000:raise ValueError('Mail attachments unavailable or too large; nothing saved')
  row=dict((k,clean(d.get(k))) for k in ('uid','type','time','rst','isRead','reason'))
  items=[];souls={};quantity=0
  for item in raw:
   if type(item) not in (list,tuple) or len(item)<2:raise ValueError('Unknown attachment structure')
   quantity+=item[1]
   info=item[2] if len(item)>2 and type(item[2]) is dict else None
   if info is not None and 'suitid' in info:
    star=info.get('qua')
    if type(star) is not int or not 1<=star<=6:raise ValueError('Unknown soul star; nothing saved')
    id=-1000-star;souls[id]=souls.get(id,0)+item[1]
    soul_names[str(id)]=str(star)+u'\u661f\u5fa1\u9b42'
   else:items.append(clean(item))
  items.extend([[id,souls[id]] for id in sorted(souls,reverse=True)])
  row.update(items=items,attachments_complete=True,reward_quantity=quantity)
  rows.append(row)
 import Globals
 result={'role':{'nickname':Globals.player1.name,'server_id':Globals.player1.server_id,'short_id':Globals.player1.short_id},'dojo_mails':rows,'loaded_count':len(mails)}
 names=dict(soul_names);config=sys.modules.get('DynamicConfigData')
 ids=set(item[0] for row in rows for item in row['items'])
 for id in ids:
  if str(id) in names:continue
  for table_name in ('DATA_CURRENCY','DATA_JJCARD','DATA_ITEM_SAMPLE','DATA_HERO'):
   try:
    table=getattr(config.__dict__.get(table_name),'data',{})
    row=table.get(id,table.get(str(id)))
    name=row.get('name') if row is not None else None
    if isinstance(name,str) or type(name).__name__=='unicode':
     if name:names[str(id)]=name[:160];break
   except Exception:pass
 result['item_names']=names;meta={}
 for id in ids:
  info={'name':names.get(str(id),''),'kind':'resource'}
  try:
   table=getattr(config.__dict__.get('DATA_JJCARD'),'data',{})
   card=table.get(id,table.get(str(id)))
   if card is not None:
    info['kind']='realm_card';star=card.get('star')
    if isinstance(star,int) and 1<=star<=6:info['stars']=star
  except Exception:pass
  meta[str(id)]=info
 result['item_meta']=meta
except Exception as error:result={'error':str(error)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
