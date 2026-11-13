from pathlib import Path
from unittest.mock import patch
import time,datetime as dt
import desktop_api,mail_reader,role_reader
root=Path(__file__).resolve().parent/'test-results'/('mail-batch-'+str(time.time_ns()));api=desktop_api.DesktopApi(root)
def envelope(who):
 return {'role':{'nickname':'独立角色'+str(who),'short_id':who,'server_id':10084},'loaded_count':2,'dojo_mails':[{'uid':'mail-'+str(who),'type':400179,'reason':'gym2_attack','time':int(dt.datetime.now().timestamp())-10,'items':[[490001,2],[900001,12345]]}]}
calls=[]
def read(pid,*args):
 calls.append(pid)
 if pid==20:raise OSError('测试窗口未就绪')
 return envelope(111 if pid in (10,40) else 333)
with patch.object(api,'_roles',return_value=[]),patch.object(role_reader,'game_pids',return_value={10,20,30,40}),patch.object(api._app,'process_stamp',side_effect=lambda pid:pid*100),patch.object(mail_reader,'read',side_effect=read):
 snapshot=api.blue_mail('archives')['data'];r=api.blue_mail('read_all',{'confirm':True,'revision':snapshot['revision']});assert r['ok'],r
 d=r['data'];assert calls==[10,20,30,40] and d['succeeded']==3 and d['failed']==1 and d['added']==2 and d['duplicates']==1
 archives=api.blue_mail('archives')['data'];assert len(archives['roles'])==2
 records=api.blue_mail('records')['data'];assert len(records)==2 and all(r['role_id'].startswith('resource-') for r in records)
 again=api.blue_mail('read_all',{'confirm':True,'revision':archives['revision']});assert again['ok'] and again['data']['added']==0 and len(api.blue_mail('archives')['data']['roles'])==2
 assert not api._mail_reading and not api._mail_batch_progress['active']
 assert not api.blue_mail('read_all',{'confirm':True,'revision':-1})['ok']
 api._updating=True;assert not api.blue_mail('read_all',{'confirm':True,'revision':archives['revision']})['ok'];api._updating=False
# Archive survives absence of all launcher accounts; names remain readable.
assert all(r['label'].startswith('独立角色') for r in api._blue.mail_records([]))
assert not (root/'data/accounts.json').exists() or not api._config()['accounts']
print('PASS: unregistered running roles auto-archive, failed window isolation, two windows same-role deduplication, repeat-read idempotence, stale revision/update guard and archive independence.')
