"""Three-level preference behavior and all three launch dispatch paths. No games."""
import copy,json
from pathlib import Path
from unittest.mock import Mock,patch
import game_preferences as gp
cfg={'game_preferences':{'mute_all':True,'skip_intro':False,'lowest_graphics':True},
     'accounts':[{'id':'a','game_preferences':{'mute_all':False,'lowest_graphics':None}}], 'pending':[]}
assert gp.resolve(cfg,'a')=={'mute_all':False,'skip_intro':False,'lowest_graphics':True}
assert gp.resolve(cfg,'a',{'mute_all':True,'skip_intro':None,'lowest_graphics':False})=={'mute_all':True,'skip_intro':False,'lowest_graphics':False}
assert gp.resolve(cfg,'a',{'mute_all':None})['mute_all'] is False
assert gp.resolve({'accounts':[{'id':'old'}]},'old')==gp.DEFAULTS
assert gp.overrides({'mute_all':None,'skip_intro':False})=={'skip_intro':False}
try:gp.overrides({'mute_all':'false'})
except ValueError:pass
else:raise AssertionError('invalid override accepted')
import test_desktop_api as fixture
import desktop_api
api=fixture.api
api._layout=Mock(return_value=None)
assert api.command('game_preferences',cfg['game_preferences'])['ok']
assert api.command('role_meta',{'ids':['a'],'game_preferences':{'mute_all':False,'skip_intro':None}})['ok']
base={'ids':['a'],'settings':{},'profiles':{},'screen':'fixture'}
plan_a={'mute_all':True,'lowest_graphics':False,'skip_intro':None}
plan_b={'mute_all':None,'skip_intro':True}
assert api.command('save_plan',{**base,'name':'pref-A','game_preferences':plan_a})['ok']
assert api.command('save_plan',{**base,'name':'pref-B','game_preferences':plan_b})['ok']
stored=api._config();assert stored['layout_plans']['pref-A']['game_preferences']=={'mute_all':True,'lowest_graphics':False}
assert stored['layout_plans']['pref-B']['game_preferences']=={'skip_intro':True}
assert next(x for x in stored['accounts'] if x['id']=='a')['game_preferences']=={'mute_all':False}
before=copy.deepcopy(stored)
assert not api.command('save_plan',{**base,'name':'bad','game_preferences':{'mute_all':1}})['ok']
assert not api.command('role_meta',{'ids':['a'],'game_preferences':{'mute_all':1}})['ok']
assert api._config()==before
api._app.find_game=Mock(return_value=(Path('D:/fake'),Path('D:/fake/game.exe')))
api._app.launch=Mock(return_value=(Mock(pid=123),Path('fixture')))
with patch.object(desktop_api.threading,'Thread'):
    assert api.command('single_start',{'id':'a'})['ok']
    assert api._app.launch.call_args.args[3]=={'mute_all':False,'skip_intro':False,'lowest_graphics':True}
    assert api.command('start_member',{**base,'id':'a','game_preferences':plan_a})['ok']
    expected={'mute_all':True,'skip_intro':False,'lowest_graphics':False}
    assert api._app.launch.call_args.args[3]==expected
    key=api._proxies.save({'name':'fixture','host':'127.0.0.1','port':1080})
    assert api.command('proxy_bind',{'ids':['a'],'proxy_id':key})['ok']
    api._proxy_trial_start=Mock(return_value='e'*32)
    assert api.command('start',{**base,'game_preferences':plan_a})['ok']
    assert api._proxy_trial_start.call_args.args[0]['game_preferences']==expected
    assert api.command('proxy_backend',{'backend':'laoyu'})['ok']
    api._laoyu_start=Mock(return_value='f'*32)
    assert api.command('start',{**base,'game_preferences':plan_a})['ok']
    assert api._laoyu_start.call_args.args[2]==expected
assert api._config()['layout_plans']['pref-B']['game_preferences']=={'skip_intro':True}
print('PASS: per-field scheme > role > global precedence; null inherits and false remains explicit; independent schemes; strict persistence; standalone ignores scheme; member, direct, built-in and LaoYu launch dispatch all receive identical effective settings. No games or network.')
