"""No real network, game actions, or deletion. Fixtures are retained for inspection."""
import hashlib
import io
import json
from pathlib import Path
import time
from unittest.mock import patch
import app_updates as u

root = Path(__file__).resolve().parent / 'test-results' / ('updates-' + str(time.time_ns()))
root.mkdir(parents=True)
brand = {'version': '9.47', 'release_channel': 'experimental'}
body = b'test-only archive bytes'

def row(number='9.48', experimental=True):
    tag = 'v' + number + ('-experimental' if experimental else '')
    name = 'JiangshiYys-' + number + ('-experimental' if experimental else '') + '-win-x64.zip'
    return {'tag_name': tag, 'prerelease': experimental, 'body': '<script>untrusted</script>', 'assets': [
        {'name': name, 'size': len(body), 'digest': 'sha256:' + hashlib.sha256(body).hexdigest(),
         'browser_download_url': 'https://github.com/' + u.REPO + '/releases/download/' + tag + '/' + name}]}

assert u.version('9.9') < u.version('9.10')
assert u.select_release([row()], '9.47', True)['version'] == '9.48'
assert u.select_release([row()], '9.47', False) is None
assert u.select_release([row('9.47')], '9.47', True) is None
assert u.select_release([row('9.47', False)], '9.47', True)['experimental'] is False
assert u.select_release([row('9.46')], '9.47', True) is None
assert u.select_release([row('9.48'), row('9.49', False)], '9.47', True)['version'] == '9.49'
for modify in [lambda a: a.update(digest=''), lambda a: a.update(size=u.LIMIT + 1),
               lambda a: a.update(name='../evil.zip'), lambda a: a.update(browser_download_url='https://evil.example/file.zip')]:
    item = row(); modify(item['assets'][0]); assert u.select_release([item], '9.47', True) is None
for bad in ['http://github.com/' + u.REPO + '/releases', 'https://github.com.evil.example/x',
            'https://user:password@github.com/' + u.REPO + '/releases', 'https://github.com/other/repo/releases']:
    try: u.trusted_url(bad)
    except ValueError: pass
    else: raise AssertionError('untrusted URL accepted')
manager = u.UpdateManager(root, brand)
assert manager.auto and manager.status()['phase'] == 'idle'
manager.settings(False); assert not u.UpdateManager(root, brand).auto
with patch.object(u, 'fetch', return_value=io.BytesIO(json.dumps([row()]).encode())):
    manager._work('check')
assert manager.status()['phase'] == 'available'
with patch.object(u, 'fetch', return_value=io.BytesIO(body)):
    manager._work('download')
s = manager.status(); assert s['phase'] == 'downloaded' and Path(s['path']).read_bytes() == body
assert s['received'] == len(body)
with patch.object(u, 'fetch', return_value=io.BytesIO(b'bad')):
    manager._work('download')
assert manager.status()['phase'] == 'error' and not manager.status()['path']
with patch.object(u, 'fetch', side_effect=OSError('proxy-secret-example')):
    manager._work('check')
assert 'proxy-secret-example' not in str(manager.status())
manager.busy = True
with patch.object(u.threading, 'Thread') as thread:
    manager.start('check'); thread.assert_not_called()
import desktop_api
api = desktop_api.DesktopApi(root / 'bridge')
assert api.update('status')['ok']
assert api.update('settings', {'auto_check': False})['ok']
with patch.object(api._updates, 'start') as start:
    assert api.update('startup')['ok']; start.assert_not_called()
assert not api.update('arbitrary')['ok']
assert not api.update('folder')['ok']
print('PASS: version channels, trusted URLs, digest requirement, verified download, corrupt/failed network, nonblocking guard, settings, bridge; no user data or game touched')

manager = u.UpdateManager(root / 'fallback', brand)
with patch.object(u, 'fetch', side_effect=[OSError('raw unavailable'), io.BytesIO(json.dumps([row()]).encode())]) as mocked:
    manager._work('check')
    assert mocked.call_args_list[0].args == (u.MANIFEST,)
    assert mocked.call_args_list[1].args == (u.API,)
assert manager.status()['phase'] == 'available'
print('PASS: public manifest and API fallback')
