"""Single-record removal only. No file deletion, game, or remote API operations."""
import time
from pathlib import Path
from unittest.mock import Mock
import proxy_support
root=Path(__file__).resolve().parent/'test-results'/f'proxy-delete-{time.time_ns()}'
s=proxy_support.ProxyStore(root)
a=s.save({'name':'test-a','host':'127.0.0.1','port':1080})
b=s.save({'name':'keep-b','host':'127.0.0.2','port':1080})
s.remove(a)
assert s.file.is_file() and [x['id'] for x in s.public()]==[b]
try:s.remove('missing')
except proxy_support.ProxyError:pass
else:raise AssertionError('unknown deletion accepted')
line={'sign':'remote','ip':'127.0.0.3','port':1080,'type':1,'ban':False}
s.import_laoyu([line]);remote=next(x for x in s.public() if x.get('laoyu_sign'))
s.remove(remote['id']);assert s.hidden_laoyu(22999)==1
s.import_laoyu([line]);assert not any(x.get('laoyu_sign')=='remote' for x in s.public())
s.save({'id':b,'name':'renamed','host':'127.0.0.2','port':1080})
s.remember(b,{'tcp':True});assert s.hidden_laoyu(22999)==1
assert s.restore_laoyu(8091)==0 and s.hidden_laoyu(22999)==1
assert s.restore_laoyu(22999)==1
s.import_laoyu([line]);assert any(x.get('laoyu_sign')=='remote' for x in s.public())
import test_desktop_api as fixture
api=fixture.api
key=api._proxies.save({'name':'fixture','host':'127.0.0.1','port':1080})
assert api.command('proxy_bind',{'ids':['a'],'proxy_id':key})['ok']
assert not api.command('proxy_delete',{'id':key})['ok']
assert any(x['id']==key for x in api._proxies.public())
assert api.command('proxy_bind',{'ids':['a'],'proxy_id':''})['ok']
api._proxy_trial_status=Mock(return_value={'active':True,'proxy_id':key})
assert not api.command('proxy_delete',{'id':key})['ok']
other=api._proxies.save({'name':'unrelated-test','host':'127.0.0.2','port':1080})
assert api.command('proxy_delete',{'id':other})['ok']
api._proxy_trial_status.return_value={'active':False}
assert api.command('proxy_delete',{'id':key})['ok']
assert not api.command('proxy_delete',{'id':key})['ok']
assert api._config()['accounts'][0]['proxy_id']==''
print('PASS: removes only selected record; proxy file retained; bound/in-use/unknown guards; unrelated removal allowed; LaoYu refresh exclusion survives save/test; explicit restore; role configuration retained. No files deleted or external operations.')
