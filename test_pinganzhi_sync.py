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
