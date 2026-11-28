from pathlib import Path
from unittest.mock import patch,MagicMock
import threading,time
import desktop_api
root=Path(__file__).resolve().parent/'test-results'/('regular-launch-'+str(time.time_ns()));api=desktop_api.DesktopApi(root)
game=Path('D:/DemoGame');exe=game/'bin/onmyoji.exe';config={'game':str(game),'accounts':[],'pending':[]}
child=MagicMock();child.pid=123;child.poll.return_value=None
with patch.object(api,'_config',return_value=config),patch.object(api._app,'find_game',return_value=(game,exe)),patch.object(desktop_api.threading,'Thread') as thread,patch.object(api._app,'prepare') as prepare,patch.object(desktop_api.subprocess,'Popen',return_value=child) as spawn:
 r=api.regular_launch('start',{'count':3,'delay':0});assert r['ok'] and r['data']['active']
 assert not api.regular_launch('start',{'count':1})['ok']
 target=thread.call_args.kwargs;target['target'](*target['args'])
 assert spawn.call_count==3 and not prepare.called
 for call in spawn.call_args_list:assert call.args==([str(exe)],) and call.kwargs=={'cwd':game}
 assert not api.regular_launch()['data']['active'] and api.regular_launch()['data']['done']==3
 assert not (root/'data/accounts.json').exists() and not (root/'data/profiles').exists()
 for count in (0,21,True,1.5):assert not api.regular_launch('start',{'count':count})['ok']
 assert not api.regular_launch('start',{'count':1,'delay':-1})['ok']
 # Stop means only cancel future dispatches, never terminate existing games.
 api._regular_status={'active':True,'done':0,'total':3,'results':[]};cancel=threading.Event();cancel.set()
 spawn.reset_mock();api._regular_worker(game,exe,3,0,cancel);assert not spawn.called and api._regular_status['stopped'];assert not child.terminate.called
 api._regular_status={'active':True,'done':0,'total':2,'results':[]};spawn.side_effect=[OSError('test failure'),child]
 api._regular_worker(game,exe,2,0,threading.Event());assert [x['ok'] for x in api._regular_status['results']]==[False,True]
 api._updating=True;assert not api.regular_launch('start',{'count':1})['ok']
print('PASS: original executable/directory and inherited environment, no profile/role creation, count limits, concurrent launch guard, stop without closing games, failure isolation and update guard.')
