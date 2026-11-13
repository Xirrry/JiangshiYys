import json,sys
try:
 m=sys.modules['com.MailData']
 rows=[]
 def clean(v):
  if type(v) in (list,tuple):return [clean(x) for x in v[:100]]
  if type(v) in (int,str,float,bool) or v is None:return v
  if type(v).__name__ in ('long','unicode'):return v
  return None
 for mail in m.__dict__.get('mailDataList',[])[:100]:
  d=mail if type(mail) is dict else object.__getattribute__(mail,'__dict__')
  if d.get('type') != 400175 and (str(d.get('reason','')).startswith(('gym','dojo')) or d.get('type') == 400179):
   rows.append(dict((k,clean(d.get(k))) for k in ('uid','type','time','rst','isRead','reason','items','show_items')))
 import Globals
 result={'role':{'nickname':Globals.player1.name,'server_id':Globals.player1.server_id,'short_id':Globals.player1.short_id},'dojo_mails':rows,'loaded_count':len(m.__dict__.get('mailDataList',[]))}
 names={}
 config=sys.modules.get('DynamicConfigData')
 ids=set(item[0] for row in rows for item in row.get('items',[]) if type(item) is list and len(item)>=2)
 for id in ids:
  for table_name in ('DATA_CURRENCY','DATA_JJCARD'):
   try:
    table=getattr(config.__dict__.get(table_name),'data',{})
    row=table.get(id,table.get(str(id)))
    name=row.get('name') if row is not None else None
    if isinstance(name,str) and name:
     names[str(id)]=name[:160];break
   except Exception:pass
 result['item_names']=names
 meta={}
 for id in ids:
  info={'name':names.get(str(id),''),'kind':'resource'}
  try:
   table=getattr(config.__dict__.get('DATA_JJCARD'),'data',{})
   card=table.get(id,table.get(str(id)))
   if card is not None:
    info['kind']='realm_card'
    star=card.get('star')
    if isinstance(star,int) and 1<=star<=6:info['stars']=star
  except Exception:pass
  meta[str(id)]=info
 result['item_meta']=meta
except Exception as error:result={'error':str(error)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
