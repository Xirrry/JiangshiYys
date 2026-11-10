"""No game or driver starts: bridge guards and cleanup contract only."""
import copy
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
import test_desktop_api as fixture
import desktop_api
api = fixture.api
before = copy.deepcopy(api._config())
key = api._proxies.save({'name':'fixture', 'host':'127.0.0.1', 'port':1080})
assert not api.command('proxy_trial_start', {'role_id':'missing','proxy_id':key})['ok']
assert not api.command('proxy_trial_start', {'role_id':'a','proxy_id':'missing'})['ok']
child = Mock(pid=12345)
with patch.object(desktop_api.subprocess, 'Popen', return_value=child) as spawn, patch.object(api._app, 'process_stamp', return_value=777):
    result = api.command('proxy_trial_start', {'role_id':'a','proxy_id':key})
    assert result['ok'], result
    args = spawn.call_args.args[0]
    assert '--role' in args and '--proxy' in args and '--ticket' in args
    assert __import__('json').loads(args[args.index('--game-prefs')+1])=={'mute_all':True,'skip_intro':True,'lowest_graphics':True}
    assert args[args.index('--role')+1] == 'a'
    assert 'password' not in str(args)
    assert api._proxy_trial_status()['active']
    assert not api.command('proxy_trial_start', {'role_id':'b','proxy_id':key})['ok']
    assert not api.command('single_start', {'id':'a'})['ok']
    assert spawn.call_count == 1
assert api._config() == before, 'Experiment must not modify role bindings or plans'
script = Path(desktop_api.ROOT) / 'proxy-engine-experiment/game_tcp_trial.py'
spec = importlib.util.spec_from_file_location('trial_test', script)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
events=[]
k=Mock()
k.TerminateProcess.return_value=False
with patch.object(trial, 'alive', side_effect=[True,True,False]), patch.object(trial.time,'sleep',side_effect=lambda _:events.append('wait')):
    report={}
    trial.ensure_owned_exit(k, 123, report, lambda:events.append('persist'))
assert report['owned_game_exit_confirmed']
assert not report['owned_test_game_stop_requested']
assert events == ['persist','wait'], 'Failed termination must retain capture until confirmed exit'
print('PASS: explicit role/proxy, duplicate and ordinary-launch guards, credential-free child command, unchanged plans/bindings, cleanup waits for owned exit. No game/driver started.')
