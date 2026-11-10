"""Request identity prevents old workers from editing a new launch."""
from pathlib import Path
from unittest.mock import Mock,patch
import test_desktop_api as fixture
import desktop_api
api=fixture.api
api._launch_status['a']={'phase':'starting','error':'','request_id':'new'}
assert not api._launch_result('a','ready','',{'request_id':'old'})
assert api._launch_status['a']['phase']=='starting'
with patch.object(desktop_api.window_layout,'act') as act:
    api._title_later('a',{'request_id':'old'})
    act.assert_not_called()
assert api._launch_result('a','ready','',{'request_id':'new'})
api._launch_status['a']['phase']='cancelled'
assert not api._launch_result('a','ready','',{'request_id':'new'})
api._app.find_game=Mock(return_value=(Path('D:/fake'),Path('D:/fake/game.exe')))
api._app.launch=Mock(return_value=(Mock(pid=123),Path('fixture')))
with patch.object(desktop_api.threading,'Thread'):
    result=api.command('start',{'ids':['a'],'request_id':'retry-new'})
assert result['ok'],result
assert api._launch_status['a']=={'phase':'starting','error':'','request_id':'retry-new'}
with patch.object(desktop_api.window_layout,'terminate_tracked',return_value=True):
    assert api.command('close',{'ids':['a'],'force':True})['ok']
assert api._launch_status['a']['phase']=='cancelled' and api._launch_status['a']['request_id']=='retry-new'
assert not api.command('start',{'ids':['a'],'request_id':{}})['ok']
print('PASS: stale worker cannot mark ready or touch windows; current request tagged; cancellation retains identity; old completion cannot overwrite cancellation; malformed token rejected. No games or windows operated.')
