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

# Cancellation keeps partial files inert and resets the install guard.
manager = u.UpdateManager(root / 'cancel', brand)
manager.root.mkdir()
manager.state.update(release=u.select_release([row()], '9.47', True), phase='downloading')
manager.busy = True
manager.cancel()
with patch.object(u, 'fetch', return_value=io.BytesIO(body)):
    manager._work('download')
assert manager.status()['phase'] == 'cancelled' and not manager.status()['path']
import urllib.error
assert '限流' in u.failure_message(urllib.error.HTTPError(u.API, 403, '', {}, None))
assert '超时' in u.failure_message(TimeoutError())
assert '空间' in u.failure_message(OSError(28, 'private detail'))
assert '权限' in u.failure_message(PermissionError())
assert '校验' in u.failure_message(u.UpdateFailure('校验失败'))
assert u.select_release([None, 'bad', {'tag_name':'v9.99','assets':None}, row()], '9.47', True)['version']=='9.48'

# Prepare an automatic install using a synthetic archive and a mocked handoff.
import zipfile
fixture = root / 'install'
fixture.mkdir()
(fixture / 'update-downloads').mkdir()
(fixture / 'ApplyUpdate.exe').write_bytes(b'fixture-only-not-executed')
(fixture / 'data').mkdir()
(fixture / 'data' / 'keep.txt').write_text('private-fixture', encoding='utf-8')
name='JiangshiYys-9.51-experimental-win-x64.zip'
archive=fixture / 'update-downloads' / name
with zipfile.ZipFile(archive,'w') as z:
    for n,v in {'brand.json':json.dumps({'version':'9.51','name':'Fixture'}), '僵尸痒痒鼠.exe':'dummy', 'yys_core.pyd':'dummy', 'runtime/pythonw.exe':'dummy', 'frontend/dist/index.html':'dummy'}.items():
        z.writestr(name[:-4]+'/'+n,v)
rel={'name':name,'version':'9.51','size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
manager=u.UpdateManager(fixture,{'version':'9.50','name':'Fixture'})
manager.state.update(release=rel,path=str(archive),phase='downloaded')
jobs=[];manager.install_callback=jobs.append
manager._work('install')
assert manager.status()['phase']=='restarting' and len(jobs)==1
assert (jobs[0]/'new'/'brand.json').is_file()
assert not (jobs[0]/'new'/'data').exists()
assert (fixture/'data'/'keep.txt').read_text()=='private-fixture'
# A traversal-bearing archive must be rejected before extraction/handoff.
with zipfile.ZipFile(archive,'w') as z:z.writestr(name[:-4]+'/../escape.txt','bad')
rel.update(size=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
manager.state.update(phase='downloaded',path=str(archive));jobs.clear();manager._work('install')
assert manager.status()['phase']=='error' and not jobs
assert not (root/'escape.txt').exists()
# Ordinary game/device windows and dormant proxy bindings do not block updates.
with patch.object(api, '_roles', return_value=[{'id':'live','proxy_id':'saved-only'}]), \
     patch.object(api, '_state', side_effect=AssertionError('ordinary games must not be probed')), \
     patch.object(api, '_device_session_alive', side_effect=AssertionError('device sessions must not block')), \
     patch.object(api, '_proxy_routes', return_value={'live':{'active':False}}):
    api._check_update_idle()
for provider in ('builtin','laoyu'):
    with patch.object(api, '_proxy_routes', return_value={'live':{'active':True,'provider':provider}}):
        try: api._check_update_idle()
        except ValueError as error: assert '使用软件代理' in str(error)
        else: raise AssertionError('active proxy session allowed through installer')
# Install requires explicit confirmation and refuses active launch operations.
assert not api.update('install',{})['ok']
api._launch_status={'a':{'phase':'starting'}}
assert not api.update('install',{'confirm':True})['ok']
api._launch_status={};api._updating=True
assert not api.command('add')['ok'];api._update_failed();assert not api._updating
print('PASS: cancellation, actionable errors, malformed rows, safe install staging, traversal rejection and install guards; original fixture data unchanged')
