import importlib.machinery
import importlib.util
import json
from pathlib import Path
import time
import pinganzhi_sync
import role_reader
import cache_import

root = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('launcher', str(root / 'launcher.pyw'))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)
test = root / 'test-results' / f'pinganzhi-sync-{time.time_ns()}'
source = test / 'desktop-accounts'
game = test / 'game'
(game / 'bin').mkdir(parents=True)

def fixture(key, nickname, ready=True):
    account = source / key
    docs = account / 'profile/game/Documents'
    cache = account / 'profile/AppData/Roaming/Netease/Mpay'
    docs.mkdir(parents=True)
    cache.mkdir(parents=True)
    (account / 'account.json').write_text(json.dumps({'id': key, 'nickname': nickname,
        'server': '循光世', 'ready': ready, 'running': False, 'processId': 987654}), encoding='utf-8')
    config = {'areaSetId': '10084', 'local_all_login_record': {key: {'10084': [{
        'player_id': 123 if key == 'first' else 456, 'server_id': '10084',
        'player_name': nickname, 'player_level': 60, 'server_name': '循光世'}]}}}
    (docs / 'clientconfig').write_text(json.dumps(config, ensure_ascii=False).encode().hex())
    (cache / 'game-mpay.db').write_bytes(key.encode() + b'-account-cache')
    (cache / 'ignore.log').write_bytes(b'not-auth-data')
    return cache

a = fixture('first', '第一个')
b = fixture('second', '第二个')
fixture('unready', '未保存', False)
fixture('recycle', '回收账号')
sources = pinganzhi_sync.scan_accounts(source)
assert len(sources) == 2
selected = next(s for s in sources if s['meta']['id'] == 'first')
old = role_reader.game_pids
role_reader.game_pids = lambda: set()
try:
    role, count = pinganzhi_sync.sync_account(app.prepare, test / 'destination', game, selected, [])
finally:
    role_reader.game_pids = old
profile = app.account_folder(test / 'destination', role['id'])
cache = profile / 'AppData/Roaming/Netease/Mpay'
assert (cache / 'game-mpay.db').read_bytes() == b'first-account-cache'
assert count == 1 and not (cache / 'ignore.log').exists()
assert (a / 'game-mpay.db').read_bytes() == b'first-account-cache'
assert (b / 'game-mpay.db').read_bytes() == b'second-account-cache'
assert role['nickname'] == '第一个' and role['confirmed']
assert role['pinganzhi_source_id'] == 'first' and role['cache_mode'] == 'pinganzhi-account'
assert role['short_id'] == '123'
assert len(list((test / 'destination').iterdir())) == 1
role_reader.game_pids = lambda: {987654}
try:
    try:
        pinganzhi_sync.sync_account(app.prepare, test / 'blocked-destination', game, selected, [])
        raise AssertionError('Running source was copied')
    except ValueError:
        pass
finally:
    role_reader.game_pids = old
assert not hasattr(cache_import, 'locate_source')
assert not hasattr(cache_import, 'import_selected')
print('PASS: selected Pinganzhi account only, other accounts untouched, source preserved, running-source refusal, recycle/unready excluded, original-game import removed.')
print('Artifacts:', test)

# Workspace import: stable source identifiers, partial selections and local edits.
workspace = source.parent / 'desktop-multi'
workspace.mkdir()
file = workspace / 'Config.json'
config = {'accountDefaultWindowCount':2,'profiles':[{'launchMode':'account','windowCount':2,'state':{
    'windows':[{'id':'w1','groupName':'来源分组'},{'id':'w2','groupName':'来源分组'}],
    'layoutPresets':[{'id':'preset1','name':'来源方案','layout':{'columns':2,'mode':'grid'},
        'windows':[{'id':'w1','autoStart':True,'width':640,'height':360}, {'id':'w2','autoStart':True}]}]}}]}
file.write_text(json.dumps(config),encoding='utf-8')
selected['meta']['windowId']='w1'
cfg={'accounts':[role],'pending':[],'layout_plans':{}}
assert pinganzhi_sync.merge_workspace(cfg,source,{'first':selected})==1
assert role['group']=='来源分组'
plan=cfg['layout_plans']['来源方案'];assert plan['roles']==[role['id']]
assert plan['windows'][role['id']]['width']==640
plan['launch_delay']=5;role['group']='本地分组'
assert pinganzhi_sync.merge_workspace(cfg,source,{'first':selected})==0
assert len(cfg['layout_plans'])==1 and plan['launch_delay']==5 and role['group']=='本地分组'
second=next(x for x in sources if x['meta']['id']=='second');second['meta']['windowId']='w2'
cfg['accounts'].append({'id':'local-second','pinganzhi_source_id':'second','pinganzhi_source_root':str(source.resolve())})
assert pinganzhi_sync.merge_workspace(cfg,source,{'first':selected,'second':second})==0
assert plan['roles']==[role['id'],'local-second']
# Same-name local scheme is not overwritten by a different source preset.
config['profiles'][0]['state']['layoutPresets'][0]['id']='preset2'
config['profiles'][0]['state']['layoutPresets'][0]['windows'][0]['width']=800
file.write_text(json.dumps(config),encoding='utf-8')
assert pinganzhi_sync.merge_workspace(cfg,source,{'first':selected,'second':second})==1
assert len(cfg['layout_plans'])==2 and plan['launch_delay']==5
assert pinganzhi_sync.merge_workspace(cfg,source,{'first':selected,'second':second})==0
assert pinganzhi_sync.cache_digest(selected['cache'],selected['config_file'])==pinganzhi_sync.cache_digest(cache,profile/'game/Documents/clientconfig')
# Repeat sync must not allocate another cache directory or change role identity.
import desktop_api
from unittest.mock import patch
bridge=desktop_api.DesktopApi(test/'bridge')
bridge._sources={'first':selected}
repeat={'game':str(game),'accounts':[role],'pending':[]}
with patch.object(bridge,'_config',return_value=repeat), patch.object(bridge,'_save'), patch.object(bridge._app,'find_game',return_value=(game,game/'bin/onmyoji.exe')), \
     patch.object(bridge,'_running',return_value=False), patch.object(bridge,'_state',return_value={}), \
     patch.object(bridge._app,'account_folder',return_value=profile), \
     patch.object(pinganzhi_sync,'ensure_source_idle'), \
     patch.object(pinganzhi_sync,'sync_account',side_effect=AssertionError('duplicate cache allocation')):
    result=bridge._sync({'ids':['first','first']})
    assert len(result)==1 and result[0]['skipped'] and result[0]['role']==role['id']
print('PASS: account groups and presets, repeat source/content deduplication, partial-member supplementation, local edit preservation, same-name conflict safety and unchanged-cache skip.')
