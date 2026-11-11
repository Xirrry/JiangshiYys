"""Only an isolated fixture ledger. No web project/data/network or file deletion."""
from pathlib import Path
from unittest.mock import patch
import copy,datetime as dt,json,time
from blue_tickets import BlueStore
root=Path(__file__).resolve().parent/'test-results'/('blue-'+str(time.time_ns()))
roles=[{'id':'a','nickname':'A','server':'一区'},{'id':'b','nickname':'B','server':'二区'}]
store=BlueStore(root)
s=store.load(roles);assert s['revision']==0 and not s['records'] and not any(r['selected'] for r in s['roles'])
s=store.subjects(['a'],s['revision'],roles)
row={'role_id':'a','date':'2026-10-30','mode':'daily','first':0,'second':None,'firstState':'recorded','secondState':'unknown','note':'已知0与未知不同'}
s=store.save([row],s['revision'],False,roles);assert s['records'][0]['first']==0 and s['records'][0]['second'] is None
assert len(store.history('a',row['date']))==1
s=store.save([row],s['revision'],False,roles);assert len(store.history('a',row['date']))==1
# Batch failure is atomic, including a valid first entry.
before=copy.deepcopy(s);changed={**row,'first':2}
try:store.save([changed,{**row,'role_id':'b'}],s['revision'],False,roles)
except ValueError:pass
else:raise AssertionError('unselected role accepted')
assert store.load(roles)==before
# Independent store instances cannot overwrite an unseen revision.
other=BlueStore(root)
try:other.save([changed],s['revision']-1,False,roles)
except ValueError:pass
else:raise AssertionError('stale revision accepted')
x={'role_id':'a','date':row['date'],'mode':'xiajian','blue':3,'fragments':0,'eggs':1,'note':'狭间'}
try:store.save([x],s['revision'],False,roles)
except ValueError:pass
else:raise AssertionError('source replacement lacked confirmation')
s=store.save([x],s['revision'],True,roles);assert len(s['records'])==1 and s['records'][0]['mode']=='xiajian' and s['records'][0]['first'] is None
for invalid in [{**row,'first':True},{**row,'first':-1},{**row,'date':'2026-02-30'},{**x,'date':'2026-11-02'},{**row,'note':'x'*501},{**row,'date':'9999-12-31'}]:
 try:store.save([invalid],s['revision'],True,roles)
 except ValueError:pass
 else:raise AssertionError('invalid record accepted')
s=store.subjects([],s['revision'],roles);assert len(s['records'])==1 and not any(r['selected'] for r in s['roles'])
try:store.save([x],s['revision'],True,roles)
except ValueError:pass
else:raise AssertionError('deselected role modified')
archived=store.load([]);assert len(archived['records'])==1 and archived['roles'][0]['active'] is False
s=store.subjects(['a'],s['revision'],roles);s=store.save([{**x,'remove':True}],s['revision'],False,roles)
assert not s['records'] and len(store.history('a',row['date']))==3
assert all('order' not in json.dumps(r) for r in s['records'])
# Exercise actual desktop bridge using this separate data root.
import desktop_api
api=desktop_api.DesktopApi(root/'bridge');api._app.write_json(api._app.CONFIG,{'accounts':roles,'pending':[]})
assert api.blue_records('load')['ok'];assert not api.blue_records('orders')['ok']
assert not api.blue_records('save',{'rows':[row],'revision':0})['ok']
api._updating=True;assert not api.blue_records('subjects',{'ids':['a'],'revision':0})['ok']
print('PASS: default opt-in only, zero/unknown states, atomic batches, cross-instance conflicts, source replacement, validation, preserved historical roles, audit on withdrawal, local bridge; no user data or network')

# Failed commits do not report success or expose partial changes.
import sqlite3
s=store.load(roles);s=store.subjects(['a'],s['revision'],roles);before=copy.deepcopy(s)
original_connect=store._connect
class FailedCommit:
    def __init__(self):self.connection=original_connect()
    def __getattr__(self,name):return getattr(self.connection,name)
    def commit(self):raise sqlite3.OperationalError('fixture commit failure')
with patch.object(store,'_connect',side_effect=FailedCommit):
    try:store.save([row],s['revision'],False,roles)
    except sqlite3.OperationalError:pass
    else:raise AssertionError('commit failure reported as success')
assert store.load(roles)==before
print('PASS: transaction commit failure rolls back all record and audit changes')

# Native export uses the chosen filename and cannot turn it into a path.
import sys,types,base64
from unittest.mock import Mock
target=root/'fixture-report.png';dialog=Mock(return_value=(str(target),))
fake=types.SimpleNamespace(windows=[types.SimpleNamespace(create_file_dialog=dialog)],FileDialog=types.SimpleNamespace(SAVE=1))
api._updating=False
with patch.dict(sys.modules,{'webview':fake}):
    payload={'kind':'png','content':base64.b64encode(bytes.fromhex('89504e470d0a1a0a')+b'fixture').decode(),'filename':'role-report.png'}
    assert api.blue_export(payload)['ok']
    assert dialog.call_args.kwargs['save_filename']=='role-report.png'
    assert not api.blue_export({**payload,'filename':'../outside.png'})['ok']
    assert not api.blue_export({**payload,'filename':'wrong.json'})['ok']
assert target.read_bytes().startswith(bytes.fromhex('89504e470d0a1a0a'))
print('PASS: native report filename, explicit selected fixture destination and path-like filename refusal')
