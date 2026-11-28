"""Executed by the bundled runtime inside a disposable copy of the release."""
from pathlib import Path
import ctypes
import importlib
import json
import subprocess
import sys
from unittest.mock import patch,Mock

root=Path.cwd()
assert sys.flags.isolated and sys.flags.ignore_environment
assert Path(sys.executable).parent==root/'runtime'
assert not any('site-packages' in p or 'Python312' in p for p in sys.path)
import yys_core
modules=['app','desktop_api','business','cache_import','close_guard','game_preferences','game_discovery','profile_cleanup',
         'laoyu_controller','laoyu_support','launcher_workspace','pinganzhi_sync','proxy_dns','proxy_support',
         'task_checklist','shop_checklist','weekly_shops','window_groups','mystery_shop','bounty_tasks','bounty_transport','blue_tickets','mail_reader','server_merges','single_instance','app_updates','device_identity','role_reader','window_layout','game_tcp_trial','trial_job','dns_bridge','module_properties']
for name in modules:
    module=importlib.import_module('yys_core.'+name)
    assert hasattr(module,'__compiled__'),name
from yys_core import desktop_api,game_preferences,game_discovery,profile_cleanup,game_tcp_trial,business
assert desktop_api.ROOT==root and business.ROOT==root and game_tcp_trial.ROOT==root
assert game_tcp_trial.HERE==root/'proxy-engine-experiment'
import webview,clr,ssl,tkinter
assert importlib.util.find_spec('proxy_tools') is None
from yys_core.module_properties import module_property
assert list(module_property(lambda:[1,2]))==[1,2]
assert module_property(lambda:[3])[0]==3
from yys_core import device_identity
profile=device_identity.new_profile();assert not profile['enabled'] and device_identity.normalize(profile)==profile
assert (root/'hardware/IdentityView.dll').is_file()
api=desktop_api.DesktopApi()
s=api.snapshot();assert not s['config']['accounts'] and not s['config']['pending'] and not s['proxies']
ctypes.CDLL(str(root/'proxy-engine-experiment/bin/YysProxyCore.dll'))
print('PASS: native core modules, isolated runtime, dependency imports, empty user data, native DLL load; no driver started',flush=True)
fixture=root/'compiled-fixture';(fixture/'data').mkdir(parents=True)
api=desktop_api.DesktopApi(fixture)
api._save({'game':str(fixture/'game'),'accounts':[{'id':'a','nickname':'fixture','confirmed':True,'proxy_id':'fake'}],'pending':[]})
exe=fixture/'game/bin/onmyoji.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'not-executed')
found=game_discovery.discover(api._app.find_game,'',[('fixture',lambda:[str(exe)])])
assert len(found['candidates'])==1
prefs=game_preferences.resolve({'game_preferences':{'mute_all':True},'accounts':[{'id':'a','game_preferences':{'mute_all':False}}]},'a',{'mute_all':True})
assert prefs['mute_all'] is True
# Verify controller command lines without creating a game, calling LaoYu, or asking for elevation.
with patch.object(desktop_api.subprocess,'Popen',return_value=Mock(pid=123456)) as popen,patch.object(api,'_running',return_value=False),patch.object(api._app,'process_stamp',return_value=1),patch.object(api._proxies,'spec',return_value={'id':'fake'}):
    api._laoyu_start('a','fake')
    args=popen.call_args.args[0];assert args[1:4]==['-c','import yys_core; yys_core.main()','--laoyu']
    api._proxy_trial_start({'role_id':'a','proxy_id':'fake'})
    args=popen.call_args.args[0];assert args[1:4]==['-c','import yys_core; yys_core.main()','--tcp']
for mode in ['--tcp','--laoyu']:
    child=subprocess.run([sys.executable,'-c','import yys_core; yys_core.main()',mode,'--help'],capture_output=True,text=True)
    assert child.returncode==0,(mode,child.stderr)
print('PASS: both compiled controller entries and CLI dispatch; no games/network/elevation',flush=True)
# Compiled status endpoint must distinguish loaded from explicitly checked.
profile=device_identity.new_profile();profile['enabled']=True
cfg=api._config();cfg['accounts'][0]['device_identity']=profile;api._save(cfg)
fake_device=Mock(pid=222,stamp=333);fake_device.process_ended.return_value=False
fake_device.read_status.return_value={'active':True,'api_calls':[1,2,3,4]}
api._device_sessions['a']=fake_device
with patch.object(api,'_state',return_value={'pid':222,'stamp':333}),patch.object(api,'_running',return_value=True):
    response=api.command('device_check',{'id':'a'})
    assert response['ok'] and response['data']['phase']=='checked' and response['data']['stamp']=='333'
    assert response['data']['api_calls']==[1,2,3,4]
api._device_sessions.clear()
print('PASS: compiled on-demand device check and exact-process status tagging; no real device queries',flush=True)

cache=api._app.account_folder(fixture/'data/profiles','a')/'cache-marker'
cache.parent.mkdir(parents=True);cache.write_bytes(b'fixture')
with patch.object(api,'_running',return_value=False),patch.object(api,'_proxy_routes',return_value={}):
    assert api.command('remove_roles',{'ids':['a']})['ok']
    info=api.command('inspect_removed',{'id':'a'})['data'];assert info['bytes']==7
    assert not api.command('delete_removed',{'id':'a','confirmed':True})['ok']
    with patch.object(profile_cleanup,'execute',return_value={'bytes':7,'files':1,'removed_entries':2}) as cleanup:
        assert api.command('delete_removed',{'id':'a','confirmed':True,'cleanup_token':info['token']})['ok']
        assert Path(cleanup.call_args.args[1]['root'])==cache.parent
    assert not api._config()['removed_roles']
assert cache.exists() # API cleanup was mocked to avoid directory deletion during release verification.
single=fixture/'single/profiles/role';single.mkdir(parents=True)
marker=single/'one-test-marker';marker.write_bytes(b'one-file-test')
assert marker.resolve().is_relative_to(fixture.resolve())
with patch.object(profile_cleanup.os,'rmdir'):
    profile_cleanup.execute(single.parent,profile_cleanup.inspect(single.parent,single))
assert not marker.exists()
print('PASS: compiled game discovery, preference precedence, removal preview/token/delegation and one explicit test marker unlink; no user cache or directory deleted',flush=True)

assert api.update('status')['ok']
assert api.update('settings', {'auto_check': False})['ok']
assert api.update('startup')['data']['auto_check'] is False
assert not api.update('arbitrary')['ok']
print('PASS: compiled update bridge and preferences; no network requested')

assert (root/'ApplyUpdate.exe').is_file()
assert not api.update('install', {})['ok']
from yys_core import single_instance
instance=single_instance.Instance('Local\\JiangshiYys-compiled-selftest-'+str(__import__('os').getpid()))
assert not instance.duplicate
instance.close()
print('PASS: compiled singleton, native helper presence and explicit install confirmation guard')

cfg=api._config();cfg['accounts']=[{'id':'blue-fixture','nickname':'blue-fixture','confirmed':True}];cfg['pending']=[];api._save(cfg)
blue=api.blue_records('load')
assert blue['ok'] and not blue['data']['records'] and not any(r['selected'] for r in blue['data']['roles'])
blue_role=api._roles()[0]['id']
blue=api.blue_records('subjects',{'ids':[blue_role],'revision':blue['data']['revision']})
assert blue['ok']
blue=api.blue_records('save',{'revision':blue['data']['revision'],'rows':[{'role_id':blue_role,'date':'2026-10-30','mode':'daily','first':0,'second':None,'firstState':'recorded','secondState':'unknown','note':'compiled-fixture'}]})
assert blue['ok'] and blue['data']['records'][0]['first']==0 and blue['data']['records'][0]['second'] is None
assert len(api.blue_records('history',{'role_id':blue_role,'date':'2026-10-30'})['data'])==1
assert not api.blue_records('orders')['ok']
print('PASS: compiled local blue ledger, opt-in subjects, persisted zero/unknown, history and no business endpoints; no network')

export_target=fixture/'blue-fixture-export.csv'
with patch.object(webview,'windows',[Mock(create_file_dialog=Mock(return_value=(str(export_target),)))]):
    assert api.blue_export({'kind':'csv','content':'role,date,first\nfixture,2026-10-30,0'})['ok']
assert export_target.read_bytes().startswith(bytes.fromhex('efbbbf'))
assert not api.blue_export({'kind':'png','content':'bm90LXBpbmc='})['ok']
print('PASS: compiled export bridge writes selected fixture only and rejects invalid PNG')

from yys_core import server_merges
assert server_merges.ROOT==root and server_merges.same_server('10001','10003')
assert callable(api.running_windows)
print('PASS: bundled official server equivalence and runtime-window API')

from yys_core.close_guard import WindowSizeMemory
prefs=WindowSizeMemory(fixture/'data/window-state.json',(1480,980),(1920,1080),(1120,680))
assert prefs.capture(Mock(native=None,width=1300,height=820))
assert WindowSizeMemory(fixture/'data/window-state.json',(1480,980),(1920,1080),(1120,680)).size==(1300,820)
assert (root/'hardware/bounty-reader/bounty_agent.dll').is_file()
assert (root/'hardware/shop-reader/shop_agent.dll').is_file()
assert callable(api.bounty_tasks) and callable(api.mystery_shop)
print('PASS: compiled window-size persistence and bounty/shop modules/reader components; no game reads')

# v9.57 release-critical functionality, using retained synthetic data only.
from yys_core import task_checklist, window_layout
check_root=fixture/'release957';check_api=desktop_api.DesktopApi(data_root=check_root)
consent=check_api.usage_consent()['data'];assert not consent['accepted']
assert not check_api.usage_consent('accept',{'version':consent['version'],'agreed':False})['ok']
assert check_api.usage_consent('accept',{'version':consent['version'],'agreed':True})['data']['accepted']
assert desktop_api.DesktopApi(data_root=check_root).usage_consent()['data']['accepted']
store=task_checklist.ChecklistStore(check_root)
for i in (1,2):store.save({'role':{'server_id':1,'short_id':i,'nickname':'fixture'},'observations':{'d0':{'status':'done','detail':'saved'}}})
store.group({'action':'reorder','roles':['1:2','1:1']});assert [r['key'] for r in store.load()['roles']]==['1:2','1:1']
store.group({'action':'hide_role','role':'1:1'});assert len(store.load()['roles'])==1 and len(store.load()['archived_roles'])==1
store.group({'action':'restore_role','role':'1:1'});assert len(store.load()['roles'])==2
assert {'lanqi_exchange','guild_kirin','guild_banquet','evening_boss'}<=task_checklist.IDS
rects=window_layout.profile_rectangles(['a','b'],[0,0,1920,1080],{},mode='反向错落',start_x=30,start_y=20,offset_x=100,offset_y=80)
assert rects['b'][0]-rects['a'][0]==100 and rects['a'][1]-rects['b'][1]==80
assert (root/'hardware/checklist-reader/checklist_agent.dll').is_file()
brand=json.loads((root/'brand.json').read_text(encoding='utf-8'));assert brand['version']=='9.58'
print('PASS: v9.57 compiled consent, checklist ordering/archive restore, new task catalog and diagonal parameters')
