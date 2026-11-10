"""Only fixture config files; preserve login data, encoding and private-path boundary."""
import copy,json,time,os
from pathlib import Path
import game_preferences as gp
root=Path(__file__).resolve().parent/'test-results'/f'game-prefs-{time.time_ns()}'
base=root/'profiles';base.mkdir(parents=True)
data={'login_secret':'fixture-private','server_id':'123','last_res_version':'keep',
      'graphics_quality_state':{'version':3,'preset':'custom','values':{'shadow':3,'msaa':1,'unknown_flag':7}},
      'msaa_switch':True,'voiceState':True,'MusicVolume':1.0,'launchVideoState':False,'unrelated':{'x':[1,2]}}
for fmt in ('plain','hex'):
    file=base/fmt/'game/Documents/clientconfig';file.parent.mkdir(parents=True)
    text=json.dumps(data,ensure_ascii=False)
    raw=(text if fmt=='plain' else text.encode().hex()).encode()
    file.write_bytes(raw)
    assert gp.apply(file,base)
    current=file.read_text(encoding='utf-8');parsed=json.loads(current if fmt=='plain' else bytes.fromhex(current))
    assert parsed==gp.patch(data)
    assert parsed['login_secret']=='fixture-private' and parsed['server_id']=='123' and parsed['unrelated']==data['unrelated']
    assert parsed['graphics_quality_state']['values']['unknown_flag']==7
    assert all(parsed['graphics_quality_state']['values'][k]==0 for k in gp.LOW_VALUES)
    assert parsed['launchVideoState'] is True and parsed['msaa_switch'] is True and parsed['graphics_quality_state']['values']['msaa']==1
    assert all(parsed[k] is False for k in ('voiceState','sfxSoundState','VideoSoundState','yuyinState'))
    assert all(parsed[k]==0.0 for k in ('MusicVolume','SfxSoundVolume','VideoSoundVolume','yuyinVolume'))
    assert file.with_name(file.name+'.before-launch-settings').read_bytes()==raw
    after=file.read_bytes();assert not gp.apply(file,base) and file.read_bytes()==after
all_off={k:False for k in gp.DEFAULTS}
assert gp.patch(data,all_off)==data
original=root/'original-config';original.write_text(json.dumps(data))
try:gp.apply(original,base)
except ValueError:pass
else:raise AssertionError('original game path accepted')
assert json.loads(original.read_text())==data
link=base/'shared-hardlink';link.hardlink_to(original)
try:gp.apply(link,base)
except ValueError:pass
else:raise AssertionError('shared hardlink accepted')
bad=base/'bad-config';bad.write_bytes(b'not-hex-or-json')
try:gp.apply(bad,base)
except ValueError:pass
else:raise AssertionError('malformed config overwritten')
assert bad.read_bytes()==b'not-hex-or-json'
try:gp.patch({'graphics_quality_state':{'version':999}})
except ValueError:pass
else:raise AssertionError('unknown graphics version overwritten')
# All real launch paths use this business prepare() before CreateProcess.
from desktop_api import DesktopApi
api=DesktopApi(root)
api._app.write_json(api._app.CONFIG,{'game':'fixture','accounts':[],'game_preferences':dict(gp.DEFAULTS)})
game=root/'fake-game';(game/'bin').mkdir(parents=True);(game/'Documents').mkdir()
(game/'bin/onmyoji.exe').write_bytes(b'fixture-not-executable')
source=game/'Documents/clientconfig';source.write_text(json.dumps({'last_res_version':'fixture-version','login_secret':'source-must-not-copy'}))
profile=api._app.account_folder(api._app.DATA/'profiles','role-a');private=profile/'game/Documents/clientconfig';private.parent.mkdir(parents=True);private.write_text(json.dumps(data))
_,cwd,env=api._app.prepare(api._app.DATA/'profiles',game,'role-a')
prepared=json.loads(private.read_text(encoding='utf-8'))
assert prepared['login_secret']=='fixture-private' and prepared['last_res_version']=='fixture-version'
assert prepared['MusicVolume']==0 and prepared['graphics_quality_state']['values']['msaa']==1 and prepared['msaa_switch'] is True
assert json.loads(source.read_text())['login_secret']=='source-must-not-copy'
assert env['APPDATA'].startswith(str(profile))
print('PASS: four sound toggles/volumes; correct inverse login-animation flag; minimum graphics fields; antialiasing settings preserved; plain/hex preservation; idempotence and original backup; login/unknown keys retained; malformed/version/path/hardlink refusal; shared prepare applies before any process launch. No game or network started.')

assert not api.command('game_preferences',{'mute_all':'false'})['ok']
assert api.command('game_preferences',all_off)['ok']
private.write_text(json.dumps(data),encoding='utf-8')
api._app.prepare(api._app.DATA/'profiles',game,'role-a')
preserved=json.loads(private.read_text(encoding='utf-8'))
assert preserved['voiceState'] is True and preserved['MusicVolume']==1.0 and preserved['launchVideoState'] is False
print('PASS: game preference API persists strict booleans; disabling enforcement leaves current game audio/graphics choices intact.')

for switch,level in [(True,1),(False,0),(True,3)]:
    fixture=copy.deepcopy(data);fixture['msaa_switch']=switch;fixture['graphics_quality_state']['values']['msaa']=level
    result=gp.patch(fixture)
    assert result['msaa_switch'] is switch and result['graphics_quality_state']['values']['msaa']==level
missing=copy.deepcopy(data);missing.pop('msaa_switch');missing['graphics_quality_state']['values'].pop('msaa')
result=gp.patch(missing);assert 'msaa_switch' not in result and 'msaa' not in result['graphics_quality_state']['values']
print('PASS: enabled, disabled, custom and absent antialiasing settings remain unchanged')
