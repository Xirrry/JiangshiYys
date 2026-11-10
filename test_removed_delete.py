"""Deletion uses a fresh server-side cleanup plan; filesystem side effects are mocked."""
from pathlib import Path
from unittest.mock import patch
import time
import desktop_api

root=Path(__file__).resolve().parent/'test-results'/f'removed-delete-{time.time_ns()}'
(root/'data').mkdir(parents=True)
api=desktop_api.DesktopApi(root)
record={'role':{'id':'a','name':'fixture'},'collection':'accounts'}
other={'role':{'id':'b','name':'other'},'collection':'pending'}
api._save({'accounts':[],'pending':[],'removed_roles':[record,other]})
cache=api._app.account_folder(root/'data/profiles','a')/'cache-marker.txt'
cache.parent.mkdir(parents=True);cache.write_text('must be retained')
before=api._config()
for payload in ({'id':'a'},{'id':'a','confirmed':1},{'id':'unknown','confirmed':True}):
    assert not api.command('delete_removed',payload)['ok']
    assert api._config()==before
with patch.object(api,'_running',return_value=True):
    assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
with patch.object(api,'_proxy_routes',return_value={'a':{'active':True}}):
    assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
cfg=api._config();cfg['accounts']=[{'id':'a'}];api._save(cfg)
assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
api._save(before)
assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
preview=api.command('inspect_removed',{'id':'a'})
assert preview['ok'] and preview['data']['bytes']==len('must be retained')
token=preview['data']['token']
# A failure keeps the record and consumes confirmation so retry needs a fresh scan.
with patch.object(desktop_api.profile_cleanup,'execute',side_effect=PermissionError('fixture locked')):
    failed=api.command('delete_removed',{'id':'a','confirmed':True,'cleanup_token':token})
assert not failed['ok'] and api._config()==before
assert not api.command('delete_removed',{'id':'a','confirmed':True,'cleanup_token':token})['ok']
preview=api.command('inspect_removed',{'id':'a'})['data']
with patch.object(desktop_api.profile_cleanup,'execute',return_value={'bytes':16,'files':1,'removed_entries':2}) as cleanup:
    result=api.command('delete_removed',{'id':'a','confirmed':True,'cleanup_token':preview['token']})
    assert result['ok'],result
    assert Path(cleanup.call_args.args[1]['root'])==cache.parent.absolute()
assert result['data']['bytes']==16
assert api._config()['removed_roles']==[other]
assert cache.read_text()=='must be retained'
assert not api.command('restore_role',{'id':'a'})['ok']
assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
assert api.command('restore_role',{'id':'b'})['ok']
assert api._config()['pending']==[other['role']]
print('PASS: explicit confirmation plus fresh cleanup token, state guards, partial-failure record retention, cleanup-plan delegation, token replay refusal, only selected record removed and other role restore. User caches untouched.')
