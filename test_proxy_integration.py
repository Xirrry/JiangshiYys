"""Ordinary launch integration with fake launchers only; never starts a game/driver."""
import copy
from pathlib import Path
from unittest.mock import Mock,patch
import test_desktop_api as fixture
import desktop_api
api=fixture.api
key=api._proxies.save({'name':'integration','host':'127.0.0.1','port':1080})
api._proxy_bind({'ids':['a'],'proxy_id':key})
before=copy.deepcopy(api._config())
api._app.find_game=Mock(return_value=(Path('D:/fake'),Path('D:/fake/bin/game.exe')))
api._app.launch=Mock(return_value=(Mock(pid=123),Path('fixture-profile')))
api._layout=Mock(return_value=(['a','b'],{},[],[]))
api._proxy_trial_start=Mock(return_value='f'*32)
api._proxy_trial_status=Mock(return_value={'active':False,'phase':'idle'})
with patch.object(desktop_api.threading,'Thread'):
    for action,payload in [('single_start',{'id':'a'}),('start_member',{'id':'a','ids':['a','b']}),('start',{'ids':['a'],'layout_ids':['a','b']})]:
        result=api.command(action,payload)
        assert result['ok'],result
        data=result['data'][0] if isinstance(result['data'],list) else result['data']
        assert data['proxy'] and data['starting']
    assert api._proxy_trial_start.call_count==3
    api._app.launch.assert_not_called()
    result=api.command('start',{'ids':['b']})
    assert result['ok'],result
    assert api._app.launch.call_count==1
assert api._config()==before
api._proxy_bind({'ids':['b'],'proxy_id':key})
api._proxy_trial_start.reset_mock();api._app.launch.reset_mock()
for payload in ({'ids':['a','b']},{'ids':['a'],'layout_ids':['a','b']}):
    result=api.command('start',payload)
    assert not result['ok'] and '1 个' in result['error'],result
api._proxy_trial_start.assert_not_called();api._app.launch.assert_not_called()
api._proxy_bind({'ids':['b'],'proxy_id':''})
api._proxy_trial_status.return_value={'active':True,'role_id':'b'}
assert not api.command('start',{'ids':['a']})['ok']
api._proxy_trial_status.return_value={'active':True,'role_id':'a','ticket':'f'*32}
assert not api.command('proxy_bind',{'ids':['a'],'proxy_id':''})['ok']
with patch.object(Path,'write_text') as write:
    assert api.command('close',{'ids':['a'],'force':True})['data']==1
    write.assert_called_once_with('cancel',encoding='ascii')
api._proxy_trial_status.return_value={'active':False}
api._proxies.save({'id':key,'name':'integration','host':'127.0.0.1','port':1080,'enabled':False})
assert not api.command('single_start',{'id':'a'})['ok']
api._app.launch.assert_not_called()
# A fresh attempt may fail; the cancelled earlier attempt must remain terminal.
api._launch_status['a']={'phase':'starting','error':''}
with patch.object(api._app,'read_json',return_value={'phase':'failed','message':'fixture cancelled'}):
    api._watch_proxy_start('a','f'*32,{})
assert api._launch_status['a']=={'phase':'failed','error':'fixture cancelled'}
with patch.object(api._app,'read_json',return_value={'phase':'running_tcp_trial'}),patch.object(api,'_title_later') as title:
    options={'ids':['a'],'layout_ids':['a','b']}
    api._watch_proxy_start('a','f'*32,options)
    title.assert_called_once_with('a',options)
print('PASS: all ordinary launch entries use bound TCP route; direct roles retain direct launch; full-scheme preflight before partial launch; one-proxy capacity; disabled proxy blocks; pending binding guard; cancel signal; ready/failure feedback; plans unchanged. No games/network/drivers.')
