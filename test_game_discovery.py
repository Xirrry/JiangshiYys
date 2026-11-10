"""Discovery fixtures never start a game or scan arbitrary directories."""
from pathlib import Path
from unittest.mock import patch
import time
import game_discovery
import desktop_api

root=Path(__file__).resolve().parent/'test-results'/f'discovery-{time.time_ns()}'
root.mkdir(parents=True)
api=desktop_api.DesktopApi(root)
for name in ('one','two'):
    exe=root/name/'bin/onmyoji.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'fixture-not-executed')
one=str(root/'one');two=str(root/'two')
providers=[('运行中的游戏',lambda:iter([one,str(root/'one/bin/onmyoji.exe'),str(root/'missing')])),
           ('系统安装记录',lambda:iter([one,two]))]
result=game_discovery.discover(api._app.find_game,one,providers)
assert result['current_valid'] and len(result['candidates'])==2
assert result['candidates'][0]['sources']==['当前配置','运行中的游戏','系统安装记录']
assert game_discovery.discover(api._app.find_game,'',[])=={'current_valid':False,'candidates':[]}
def denied():raise OSError('access denied')
assert len(game_discovery.discover(api._app.find_game,'',[('blocked',denied),('ok',lambda:[one])])['candidates'])==1

def configure(value):api._save({'game':value,'accounts':[],'pending':[]})
configure(str(root/'missing'))
single={'current_valid':False,'candidates':[{'path':one,'executable':str(root/'one/bin/onmyoji.exe'),'sources':['fixture']}]}
with patch.object(game_discovery,'discover',return_value=single.copy()) as discover:
    result=api.command('detect_game',{'automatic':True});assert result['ok'] and result['data']['saved']
    assert api._config()['game']==one
with patch.object(game_discovery,'discover') as discover:
    assert api.command('detect_game',{'automatic':True})['ok'];discover.assert_not_called()
configure(str(root/'missing'))
multiple={'current_valid':False,'candidates':[{'path':one},{'path':two}]}
with patch.object(game_discovery,'discover',return_value=multiple.copy()):
    assert not api.command('detect_game',{'automatic':True})['data']['saved']
    assert api._config()['game']==str(root/'missing')
with patch.object(game_discovery,'discover',return_value=single.copy()):
    assert not api.command('detect_game',{})['data']['saved']
    assert api._config()['game']==str(root/'missing')
# A user save while detection runs must win over the older scan result.
def concurrent_save(*args):configure(two);return single.copy()
with patch.object(game_discovery,'discover',side_effect=concurrent_save):
    assert not api.command('detect_game',{'automatic':True})['data']['saved']
    assert api._config()['game']==two
print('PASS: validated candidates, dedup/source labels, missing/access-denied paths, unique auto-save, preserve valid/manual/concurrent config, multiple-match choice. No game launched.')
