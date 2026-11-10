"""Role mutations run against a separate fixture; no user cache is touched."""
import copy
import json
from pathlib import Path
import time
import desktop_api

root = Path(__file__).resolve().parent / 'test-results' / f'role-management-{time.time_ns()}'
(root / 'data').mkdir(parents=True)
original = {'accounts': [
    {'id': 'a', 'nickname': 'A', 'server': '一区', 'short_id': '1', 'server_id': '10', 'confirmed': True},
    {'id': 'b', 'nickname': 'B', 'confirmed': True}], 'pending': [{'id': 'p', 'name': '待登录'}],
    'window_profiles': {'a': {'width': 320, 'height': 180, 'x': -800}, 'b': {'width': 560}},
    'layout_plans': {'方案': {'roles': ['a', 'b', 'p'], 'windows': {'a': {'width': 320}, 'b': {'width': 560}}}},
    'last_window_positions': {'a': [0, 0, 320, 180]}}
(root / 'data/accounts.json').write_text(json.dumps(original), encoding='utf-8')
api = desktop_api.DesktopApi(root)
def call(action, payload):
    result = api.command(action, payload)
    assert result['ok'], result
    return result['data']
def cfg():
    return api.snapshot()['config']

call('role_meta', {'ids': ['a'], 'note': '主号', 'group': '日常'})
assert cfg()['accounts'][0]['note'] == '主号'
assert 'note' not in cfg()['accounts'][1]
before = cfg()
assert not api.command('role_meta', {'ids': ['a'], 'note': 'x'*201})['ok']
assert cfg() == before
assert not api.command('remove_roles', {'ids': ['a', 'unknown']})['ok']
assert cfg() == before
# All-or-nothing: one running role prevents removal of the entire selection.
real_running, real_state = api._running, api._state
api._state = lambda key: {'key': key}
api._running = lambda state: state['key'] == 'b'
assert not api.command('remove_roles', {'ids': ['a', 'b']})['ok']
api._running, api._state = real_running, real_state
assert cfg() == before

cache = api._app.account_folder(api._app.DATA / 'profiles', 'a') / 'cache-marker.txt'
cache.parent.mkdir(parents=True)
cache.write_text('retain this file', encoding='utf-8')
assert call('remove_roles', {'ids': ['a', 'p']}) == 2
deleted = cfg()
assert [a['id'] for a in deleted['accounts']] == ['b']
assert deleted['pending'] == []
assert deleted['layout_plans']['方案']['roles'] == ['b']
assert deleted['layout_plans']['方案']['windows'] == {'b': {'width': 560}}
assert 'a' not in deleted['window_profiles']
assert 'a' not in deleted['last_window_positions']
assert cache.read_text(encoding='utf-8') == 'retain this file'
assert len(deleted['removed_roles']) == 2
call('restore_role', {'id': 'a'})
restored = cfg()
a = next(a for a in restored['accounts'] if a['id'] == 'a')
assert a['note'] == '主号' and a['group'] == '日常'
assert restored['window_profiles']['a']['x'] == -800
assert restored['layout_plans']['方案']['roles'] == ['b']
call('restore_role', {'id': 'p'})
assert cfg()['pending'][0]['id'] == 'p'
assert cfg()['removed_roles'] == []
assert cache.exists()

# Synchronizing a replacement keeps local metadata, and retargets scheme geometry.
local = copy.deepcopy(before)
old = local['accounts'][0]
new = {'id': 'new', 'nickname': '改名后的A', 'confirmed': True}
api._replace_role(local, old, new)
assert new['note'] == '主号' and new['group'] == '日常'
assert local['window_profiles']['new']['width'] == 320
assert local['layout_plans']['方案']['roles'] == ['new', 'b', 'p']
assert local['layout_plans']['方案']['windows']['new'] == {'width': 320}
assert len(list((root / 'data').glob('accounts.before-vue-*.json'))) == 1
print('PASS: role metadata, deletion guards, scheme cleanup, cache retention, recovery and sync metadata preservation.')
