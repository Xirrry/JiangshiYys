"""Binding changes retire stale proxy failures without touching session reports."""
from unittest.mock import patch
import test_desktop_api as fixture
import desktop_api

api=fixture.api
root=fixture.root
request_file=root/'data/laoyu-requests.json'
trial_file=root/'data/proxy-trial-ui.json'
ticket='a'*32
report_file=root/'data/laoyu-sessions'/(ticket+'.json')
api._app.write_json(report_file, {'phase':'failed','message':'old proxy failure'})

def seed():
    cfg=api._config()
    cfg['accounts'][0]['proxy_id']='old'
    api._save(cfg)
    api._app.write_json(request_file, {'a':{'ticket':ticket,'pid':0},'b':{'ticket':'b'*32,'pid':0}})
    api._app.write_json(trial_file, {'role_id':'a','ticket':'c'*32,'pid':0})
    api._launch_status['a']={'phase':'failed','error':'old proxy failure'}

with patch.object(api,'_running',return_value=False), patch.object(api._proxies,'spec',return_value={}):
    for action in ('proxy_bind','role_meta'):
        for binding in ('','new'):
            seed()
            assert api.command(action,{'ids':['a'],'proxy_id':binding})['ok']
            assert api._launch_status['a']['error']==''
            assert not api._launch_result('a','failed','late old worker',{})
            assert 'a' not in api._app.read_json(request_file,{})
            assert 'b' in api._app.read_json(request_file,{})
            assert api._app.read_json(trial_file,{})=={}
            assert report_file.is_file()
            assert not api.snapshot()['launches']['a']['error']
            restarted=desktop_api.DesktopApi(root)
            with patch.object(restarted,'_running',return_value=False):
                assert not restarted.snapshot()['launches'].get('a',{}).get('error')
    seed()
    assert api.command('proxy_bind',{'ids':['a'],'proxy_id':'old'})['ok']
    assert api._launch_status['a']['error']=='old proxy failure'
    assert 'a' in api._app.read_json(request_file,{})
    # A running proxy cannot be rebound or have its diagnostic state cleared.
    with patch.object(api,'_running',return_value=True):
        assert not api.command('proxy_bind',{'ids':['a'],'proxy_id':''})['ok']
    assert api._launch_status['a']['error']=='old proxy failure'
print('PASS: unbind and switch clear stale failures in both APIs; polling/restart do not revive them; late worker ignored; unchanged/running bindings and other role records preserved. No games launched.')
