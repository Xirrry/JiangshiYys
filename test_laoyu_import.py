"""No network: stable imported identities, encrypted credentials and exact-line reuse."""
import json,time
from pathlib import Path
from unittest.mock import patch,Mock
import proxy_support
from laoyu_support import Client,LaoYuError
root=Path(__file__).resolve().parent/'test-results'/f'laoyu-import-{time.time_ns()}'
store=proxy_support.ProxyStore(root)
key=store.save({'name':'手动原代理','host':'127.0.0.1','port':1080,'username':'fixture-user','password':'fixture-password'})
line={'sign':'line-a','ip':'127.0.0.1','port':1080,'user':'fixture-user','password':'fixture-password','type':1,'ban':False,'check_ip':'203.0.113.7','check_area':'fixture area'}
second={**line,'sign':'line-b','ip':'127.0.0.2'}
third={**line,'sign':'line-c'} # Same credentials, distinct LaoYu identity must remain selectable.
r=store.import_laoyu([line,second,third,{'sign':'unsupported','type':3}],22999)
assert r=={'added':2,'updated':1,'skipped':1},r
rows=store.public();assert len(rows)==3
assert next(x for x in rows if x['id']==key)['name']=='手动原代理'
assert not next(x for x in rows if x['id']==key)['laoyu_managed']
ids={x['laoyu_sign']:x['id'] for x in rows}
assert store.spec(ids['line-b'])['password']=='fixture-password'
assert 'fixture-password' not in store.file.read_text(encoding='utf-8')
assert 'fixture-user' not in json.dumps(rows)
assert store.import_laoyu([line,second,third])['added']==0
assert {x['laoyu_sign']:x['id'] for x in store.public()}==ids
store.save({'id':ids['line-b'],'name':'本地别名','host':'127.0.0.2','port':1080})
changed={**second,'password':'fixture-updated-password','ban':True}
store.import_laoyu([line,changed,third])
public=next(x for x in store.public() if x['id']==ids['line-b'])
assert public['name']=='本地别名' and not public['enabled']
assert 'fixture-updated-password' not in store.file.read_text(encoding='utf-8')
store.import_laoyu([line,third])
missing=next(x for x in store.public() if x['id']==ids['line-b'])
assert missing['laoyu_missing'] and not missing['enabled']
assert len(store.records())==3 # Retain saved references rather than delete bound proxies.
client=Client()
with patch.object(client,'lines',return_value=[line,third]),patch.object(client,'call') as call:
    assert client.ensure_line(store.spec(ids['line-c']))=='line-c'
    call.assert_not_called()
with patch.object(client,'lines',return_value=[line]),patch.object(client,'call') as call:
    try:client.ensure_line(store.spec(ids['line-c']))
    except LaoYuError:pass
    else:raise AssertionError('missing imported identity silently recreated')
    call.assert_not_called()
# Manual edits detach the old remote identity instead of being overwritten on refresh.
store.save({'id':key,'name':'changed','host':'127.0.0.9','port':1080})
assert not next(x for x in store.records() if x['id']==key).get('laoyu_sign')
import test_desktop_api as fixture
api=fixture.api
api._proxies.import_laoyu([second]);remote=next(x for x in api._proxies.public() if x.get('laoyu_managed'))
api._proxy_save({'id':remote['id'],'name':'alias','host':'127.0.0.99','port':1,'clear_auth':True,'enabled':False})
saved=api._proxies.spec(remote['id'])
assert saved['name']=='alias' and saved['host']==second['ip'] and saved['password']==second['password'] and saved['enabled']
print('PASS: manual dedup preserves ID/name; distinct remote signs stay distinct; refresh preserves IDs/aliases; DPAPI redaction; vanished/disabled lines retain inactive references; exact-sign launch never recreates missing imported line; imported address/auth editing guarded. No network or games.')
