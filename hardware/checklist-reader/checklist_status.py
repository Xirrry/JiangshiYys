import json
try:
 import Globals
 p=Globals.player1
 result={'role':{'server_id':p.server_id,'short_id':p.short_id}}
 for output,name in [('_support_query','support'),('_prayer_query','prayer'),('_boss_query','boss'),('_gve_query','gve'),('_resource_query','resource'),('_mentor_query','mentor'),('_kirin_query','kirin'),('_banquet_query','banquet')]:
  query=getattr(Globals,'_yys_checklist_'+name+'_query',{})
  if name=='support':query=getattr(Globals,'_yys_checklist_support_query',{})
  result[output]={key:query.get(key) for key in ('nonce','role','ready','expired')}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
