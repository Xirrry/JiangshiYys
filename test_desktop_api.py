import json
from pathlib import Path
import time
import desktop_api
import window_layout

root = Path(__file__).resolve().parent / 'test-results' / f'vue-api-{time.time_ns()}'
(root / 'data').mkdir(parents=True)
original = {'game': 'D:/Game/yys', 'accounts': [{'id': 'a', 'name': '角色 A', 'confirmed': True},
            {'id': 'b', 'name': '角色 B', 'confirmed': True}], 'pending': []}
(root / 'data/accounts.json').write_text(json.dumps(original), encoding='utf-8')
api = desktop_api.DesktopApi(root)
old_screens = window_layout.screens
window_layout.screens = lambda: [{'id': 'screen', 'work': (0, 0, 1920, 1080), 'primary': True}]
def call(action, payload=None):
    result = api.command(action, payload)
    assert result['ok'], result
    return result['data']
try:
    assert len(api.snapshot()['config']['accounts']) == 2
    call('group', {'kind': 'new', 'name': '第一组'})
    call('group', {'kind': 'assign', 'name': '第一组', 'ids': ['a']})
    cfg = api.snapshot()['config']
    assert cfg['accounts'][0]['group'] == '第一组'
    assert 'group' not in cfg['accounts'][1]
    p = {'ids': ['a', 'b'], 'screen': 'screen', 'profiles': {'a': {'width': 320, 'height': 180}},
         'settings': {'width': 640, 'height': 360, 'columns': 2, 'gap': 8, 'padding': 8,
                      'mode': '网格排列', 'aspect': True}}
    preview = call('preview', p)
    assert preview['rects']['a'][2:] == (320, 180)
    call('window', p)
    assert call('preview', {**p, 'profiles': {}})['rects']['a'][2:] == (640, 360)
    call('save_plan', {**p, 'name': '两开方案', 'auto': False})
    cfg = api.snapshot()['config']
    assert cfg['layout_plans']['两开方案']['roles'] == ['a', 'b']
    assert cfg['layout_plans']['两开方案']['windows']['a']['width'] == 320
    assert not api.command('preview', {**p, 'ids': ['not-owned']})['ok']
    assert not api.command('arrange', p)['ok']  # no tracked games, never moved external windows
    assert call('close', {'ids': ['a']}) == 0
    assert not api.command('arbitrary-operation', {})['ok']
    assert len(list((root / 'data').glob('accounts.before-vue-*.json'))) == 1
    assert json.loads(next((root / 'data').glob('accounts.before-vue-*.json')).read_text()) == original
    # A role may belong to multiple launch schemes with independent geometry.
    call('save_plan', {**p, 'name': '方案A', 'ids': ['a'], 'profiles': {'a': {'width': 320, 'height': 180}, 'b': {'width': 999}}})
    call('save_plan', {**p, 'name': '方案B', 'ids': ['a', 'b'], 'profiles': {'a': {'width': 800, 'height': 450}}})
    stored = api.snapshot()['config']
    assert stored['layout_plans']['方案A']['roles'] == ['a']
    assert 'b' not in stored['layout_plans']['方案A']['windows']
    assert stored['layout_plans']['方案B']['roles'] == ['a', 'b']
    assert stored['layout_plans']['方案A']['windows']['a']['width'] == 320
    assert stored['layout_plans']['方案B']['windows']['a']['width'] == 800
    assert len(stored['accounts']) == 2
    call('delete_plan', {'name': '方案A'})
    stored = api.snapshot()['config']
    assert len(stored['accounts']) == 2
    assert stored['layout_plans']['方案B']['roles'] == ['a', 'b']
    assert stored['layout_plans']['方案B']['windows']['a']['width'] == 800
    print('PASS: shared role membership, independent scheme sizes, scheme deletion preserves roles and other schemes.')
    print('PASS: Vue bridge group edits, shared layout preview, independent sizes, empty override reset, plan persistence, unknown-role refusal, window guards, one-time configuration backup.')
finally:
    window_layout.screens = old_screens
