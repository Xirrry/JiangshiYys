import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('isolated_launcher', str(root / 'launcher.pyw'))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)
artifacts = root / 'test-results' / str(time.time_ns())
app.CONFIG = artifacts / 'accounts.json'
source = artifacts / 'source'
(source / 'bin').mkdir(parents=True)
(source / 'client.ini').write_text('original', encoding='utf-8')
for name in ('cloudfilesys3', 'res', 'script'):
    (source / 'Documents' / name).mkdir(parents=True)
    (source / 'Documents' / name / 'resource.dat').write_bytes(b'existing-game-resource')
(source / 'Documents' / 'clientconfig').write_text(json.dumps({
    'last_patch_version': 'test-version', 'account': 'must-not-copy',
    'local_all_login_record': ['must-not-copy'],
}).encode().hex())
base = artifacts / 'profiles'
profiles = [app.prepare(base, source, account) for account in ('test-a', 'test-b')]
assert profiles[0][0] != profiles[1][0]
for profile, cwd, env in profiles:
    assert (cwd / 'bin').is_junction()
    assert (cwd / 'bin').resolve() == (source / 'bin').resolve()
    code = 'import os,json;from pathlib import Path;p=Path(os.environ["APPDATA"])/"probe.txt";p.write_text(os.environ["USERPROFILE"]);print(json.dumps([os.getcwd(),os.environ["USERPROFILE"]]))'
    result = subprocess.run([sys.executable, '-c', code], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [str(cwd), str(profile)]
    assert (Path(env['APPDATA']) / 'probe.txt').read_text() == str(profile)
a = profiles[0][1] / 'client.ini'
a.write_text('private', encoding='utf-8')
app.prepare(base, source, 'test-a')
assert a.read_text() == 'private'
assert (source / 'client.ini').read_text() == 'original'
assert (profiles[1][1] / 'client.ini').read_text() == 'original'
assert app.process_stamp(os.getpid()) > 0
assert app.process_stamp(0x7ffffffe) is None
for profile, cwd, env in profiles:
    assert (cwd / 'Documents/cloudfilesys3').resolve() == (source / 'Documents/cloudfilesys3').resolve()
    config, _ = app.game_config(cwd / 'Documents/clientconfig')
    assert config['last_patch_version']=='test-version'
    assert 'account' not in config and 'local_all_login_record' not in config
# A pre-fix account has a partially downloaded resource folder and login config.
legacy = app.account_folder(base, 'legacy')
partial = legacy / 'game/Documents/cloudfilesys3'
partial.mkdir(parents=True)
(partial / 'partial.dat').write_bytes(b'keep-partial-download')
private_config = legacy / 'game/Documents/clientconfig'
private_config.write_text(json.dumps({'account': 'private-account', 'last_patch_version': 'old'}).encode().hex())
app.prepare(base, source, 'legacy')
assert partial.is_junction()
backups = list(partial.parent.glob('cloudfilesys3.before-resource-fix-*'))
assert len(backups) == 1
assert (backups[0] / 'partial.dat').read_bytes() == b'keep-partial-download'
config, _ = app.game_config(private_config)
assert config['account'] == 'private-account'
assert config['last_patch_version'] == 'test-version'
app.prepare(base, source, 'legacy')
assert len(list(partial.parent.glob('cloudfilesys3.before-resource-fix-*'))) == 1
print('PASS: shared downloaded resources, version markers only, partial download backups, private login preserved, repeat preparation.')
print('PASS: separate child environments and caches, shared resources, persistent private configuration, PID creation-time checks.')
print(f'Artifacts: {artifacts}')
