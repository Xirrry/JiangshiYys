import json
try:
 import Globals
 p=Globals.player1
 result={'role':{'server_id':p.server_id,'short_id':p.short_id}}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
