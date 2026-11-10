import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import role_reader

root = Path(__file__).resolve().parent
servers = json.loads((root / 'servers.json').read_text(encoding='utf-8'))['servers']
role = role_reader.parse_identity([[818240, 10084, '昔乃', 60, None]], servers)
assert role['nickname'] == '昔乃'
assert role['server'] == '循光世'
assert role['server_id'] == '10084'
assert set(role) == {'short_id', 'server_id', 'nickname', 'server', 'server_known'}
for invalid in [None, [], [[]], {'error': 'not logged in'}, [[1, 10084, '', 0]], [[None, 10084, 'n', 60]]]:
    try:
        role_reader.parse_identity(invalid, servers)
        raise AssertionError('Invalid identity was accepted')
    except ValueError:
        pass
pending = {'game': 'example', 'accounts': [], 'pending': [{'id': 'draft', 'name': '待登录'}]}
before = copy.deepcopy(pending)
confirmed = role_reader.confirm_role(pending, 'draft', role)
assert pending == before  # reading/rejecting cannot mutate the saved roles
assert not pending['accounts']
assert confirmed['accounts'][0]['confirmed'] is True
assert confirmed['accounts'][0]['id'] == 'draft'  # retain login cache directory
assert not confirmed['pending']
duplicate = {**confirmed, 'pending': [{'id': 'second', 'name': '待登录'}]}
try:
    role_reader.confirm_role(duplicate, 'second', role)
    raise AssertionError('Duplicate role was accepted')
except ValueError:
    pass
print('PASS: role/server parsing, invalid/unlogged data rejection, fresh-login guard, confirmation-only saving, stable login directory, duplicate protection.')

# Configuration-based reader must reject old logins and the wrong server.
record = {'player_id': 818240, 'server_id': '10084', 'player_name': '昔乃',
          'player_level': 60, 'server_name': '循光世', 'login_time': 2000}
config = {'areaSetId': '10084', 'local_all_login_record': {'account': {'10084': [record]}}}
assert role_reader.select_current_identity(config, servers, 1990)['nickname'] == '昔乃'
for bad, launched in [(config, 2100), ({**config, 'areaSetId': '99999'}, 1990)]:
    try:
        role_reader.select_current_identity(bad, servers, launched)
        raise AssertionError('Stale/wrong-server role was accepted')
    except ValueError:
        pass
print('PASS: current-server and fresh login timestamps checked; no external helper needed.')

if '--live' in sys.argv:
    loader = importlib.machinery.SourceFileLoader('launcher', str(root / 'launcher.pyw'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    app = importlib.util.module_from_spec(spec)
    loader.exec_module(app)
    pids = role_reader.game_pids()
    assert len(pids) == 1, f'Live test needs one game, found {len(pids)}'
    pid = next(iter(pids))
    result = role_reader.read_identity(pid, app.process_stamp(pid), app.process_stamp,
                                      Path('D:/Game/yys/Documents/clientconfig'), servers)
    print('LIVE PASS:', result['nickname'], result['server'], result['server_id'])
    print('PASS: live read used only the game configuration; no helper, injection or response file.')
