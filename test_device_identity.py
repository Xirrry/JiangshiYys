from pathlib import Path
from unittest.mock import patch,Mock
import copy,time
import device_identity as device
import desktop_api
p=device.new_profile();q=device.new_profile()
assert not p['enabled'] and p!=q and device.normalize(p)==p
for invalid in ({'enabled':True},{**p,'volume_serial':True},{**p,'mac':'01:11:22:33:44:55'},{**p,'computer_name':'too_long_name_123456'}):
    try:device.normalize(invalid);raise AssertionError('invalid profile accepted')
    except ValueError:pass
root=Path(__file__).resolve().parent/'test-results'/('device-api-'+str(time.time_ns()));(root/'data').mkdir(parents=True)
api=desktop_api.DesktopApi(root);api._save({'accounts':[{'id':'a','confirmed':True},{'id':'b','confirmed':True}],'pending':[]})
r=api.command('device_profile',{'id':'a'});assert r['ok'] and not r['data']['enabled']
assert not api._config()['accounts'][0].get('device_identity')
p['enabled']=True
assert api.command('role_meta',{'ids':['a'],'device_identity':p})['ok']
assert api._config()['accounts'][0]['device_identity']==p
assert not api._config()['accounts'][1].get('device_identity')
before=api._config()
with patch.object(api,'_running',return_value=True):
    assert not api.command('role_meta',{'ids':['a'],'device_identity':q})['ok']
    assert not api.command('device_profile',{'id':'a'})['ok']
assert api._config()==before
local=copy.deepcopy(before);old=local['accounts'][0];new={'id':'replacement','confirmed':True};api._replace_role(local,old,new)
assert new['device_identity']==p and new['device_identity'] is not old['device_identity']
with patch.object(api,'_proxy_routes',return_value={'a':{'active':True}}):
    assert not api.command('role_meta',{'ids':['a'],'device_identity':q})['ok']
with patch.object(Path,'is_file',return_value=False):
    assert not api.command('launch_preflight',{'ids':['a']})['ok']
# Failure closes exactly this tracked role and is never reported as ready.
api._launch_status['a']={'phase':'starting','error':'','request_id':'test'}
with patch.object(desktop_api.window_layout,'act'),patch.object(api,'_activate_device',side_effect=ValueError('fixture')),patch.object(api,'_close') as close:
    api._title_later('a',{'request_id':'test'})
    close.assert_called_once_with({'ids':['a'],'force':True})
assert api._launch_status['a']['phase']=='failed'
# Success attaches once for the exact PID/stamp; second title preparation reuses it.
with patch.object(api,'_state',return_value={'pid':123,'stamp':456}),patch.object(device,'Session',return_value=Mock(pid=123,stamp=456)) as session:
    api._activate_device('a',api._config()['accounts'][0]);api._activate_device('a',api._config()['accounts'][0]);assert session.call_count==1
print('PASS: role-specific stable drafts, strict input validation, default off, running/proxy guards, sync preservation, missing-component preflight, initialization-failure close, exact-process reuse. No game or hardware changes.')
