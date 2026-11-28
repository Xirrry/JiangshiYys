import sys,json
def friend_bonds():
 fd=sys.modules.get('com.FriendData');rows=getattr(fd,'friendDataList',None)
 if not isinstance(rows,(list,tuple)):return None
 bonds={}
 for friend in rows:
  try:
   server=getattr(friend,'server_id',None);short=getattr(friend,'short_id',None)
   level=friend.getIntimacyLevel()
   if type(level) is not int or not 0<=level<=3:continue
   entry={'name':str(friend.name),'level':level}
   uid=str(getattr(friend,'uid',''))
   if uid and uid.isalnum() and len(uid)<=80:bonds['uid:'+uid]=entry
   if str(server).isdigit() and str(short).isdigit() and int(short)>0:bonds[str(int(server))+':'+str(int(short))]=entry
  except Exception:continue
 return bonds
try:
 import Globals
 p=Globals.player1
 bonds=friend_bonds()
 if bonds is None:raise ValueError('好友列表尚未加载，请打开好友界面后重试')
 result={'role':{'name':str(p.name),'server_id':p.server_id,'short_id':p.short_id},'bonds':bonds}
except Exception as e:result={'error':str(e)}
f.write(json.dumps(result,ensure_ascii=True).encode('utf-8'));f.close()
