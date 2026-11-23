from pathlib import Path
from unittest.mock import patch,MagicMock
import time
import desktop_api,window_layout,role_reader
api=desktop_api.DesktopApi(Path(__file__).resolve().parent/'test-results'/('running-windows-'+str(time.time_ns())))
rows=[{'id':'1:10','pid':1,'stamp':'10','title':'A','rect':[0,0,960,570]},{'id':'2:20','pid':2,'stamp':'20','title':'B','rect':[0,0,960,570]}]
screens=[{'id':'screen','work':[1920,0,1920,1080],'primary':False}]
p={'windows':rows,'screen':'screen','settings':{'width':960,'height':540,'columns':2,'gap':8,'padding':8,'aspect':True,'mode':'网格排列'}}
with patch.object(role_reader,'game_pids',return_value={1,2}),patch.object(window_layout,'running_game_windows',return_value=rows),patch.object(window_layout,'screens',return_value=screens),patch.object(window_layout,'border',return_value=(16,39)),patch.object(window_layout,'act') as act:
 assert len(api.running_windows()['data']['windows'])==2
 r=api.running_windows('preview',p);assert r['ok'],r
 rects=r['data']['rects'];assert all(v[0]>=1920 for v in rects.values());assert not act.called
 mockapi=MagicMock();mockapi.IsIconic.return_value=0;mockapi.IsZoomed.return_value=0
 with patch.object(window_layout,'guarded_window',return_value=100),patch.object(window_layout,'api',return_value=mockapi):
  result=api.running_windows('apply',p);assert result['ok'] and all(r['ok'] for r in result['data']['results'])
  assert [c.kwargs['rectangle'] for c in act.call_args_list]==[rects[r['id']] for r in rows]
  act.reset_mock();api.running_windows('focus',{'windows':[rows[1]]});assert act.call_args.args[0]['pid']==2
  stale={**p,'windows':[{**rows[0],'id':'1:99'}]};act.reset_mock();assert not api.running_windows('apply',stale)['ok'];assert not act.called
  bad={**p,'screen':'missing'};assert not api.running_windows('apply',bad)['ok']
  act.side_effect=[ValueError('closed'),None];result=api.running_windows('apply',p);assert [r['ok'] for r in result['data']['results']]==[False,True]
  bad={**p,'settings':{**p['settings'],'mode':'自定义坐标'},'profiles':{'1:10':{'x':-10000,'y':0}}};assert not api.running_windows('preview',bad)['ok']
print('PASS: independent window inventory, shared preview/apply geometry, non-primary monitor, focus, stale process rejection, missing monitor, individual failure isolation, out-of-bounds refusal.')

with patch.object(role_reader,'game_pids',return_value={1,2}),patch.object(window_layout,'running_game_windows',return_value=rows),patch.object(window_layout,'screens',return_value=screens),patch.object(window_layout,'terminate_tracked') as close:
 result=api.running_windows('close',{'windows':[rows[1]]});assert result['ok']
 assert close.call_args.args[0]=={'pid':2,'stamp':20} and close.call_count==1
 close.reset_mock();result=api.running_windows('close',{'windows':[{'id':'2:99'}]});assert not result['ok'] and not close.called
 close.side_effect=[OSError('access denied'),True]
 result=api.running_windows('close',{'windows':rows,'stop_regular':True})
 assert [r['ok'] for r in result['data']['results']]==[False,True]
 assert api._regular_cancel.is_set()
print('PASS: individual close scope, stale window refusal, partial failure isolation and close-all cancels pending regular launches.')

with patch.object(role_reader,'game_pids',return_value={1,2}),patch.object(window_layout,'running_game_windows',return_value=rows),patch.object(window_layout,'screens',return_value=screens),patch.object(window_layout,'guarded_window',return_value=100),patch.object(window_layout,'api',return_value=mockapi),patch.object(window_layout,'act') as move:
    rect=[1920,0,960,570]
    r=api.running_windows('place',{'windows':[rows[0]],'rects':{'1:10':rect}})
    assert r['ok'] and move.call_args.kwargs['rectangle']==rect
    move.reset_mock()
    assert not api.running_windows('place',{'windows':[rows[0]],'rects':{'1:10':[-10000,0,960,570]}})['ok'] and not move.called
    assert not api.running_windows('place',{'windows':[rows[0]],'rects':{'1:10':[1920,0,100,50]}})['ok']
print('PASS: explicit canvas positions preserve dimensions, reject off-screen/small rectangles before mutation.')

# A drag uses its verified inventory, avoiding a full process scan per pointer event.
with patch.object(role_reader,'game_pids') as scan,patch.object(window_layout,'screens',return_value=screens),patch.object(window_layout,'guarded_window',return_value=100),patch.object(window_layout,'api',return_value=mockapi),patch.object(window_layout,'act') as move:
    api._window_inventory={r['id']:r for r in rows}
    result=api.running_windows('place',{'windows':[rows[0]],'rects':{'1:10':[1920,0,960,570]}})
    assert result['ok'] and not scan.called and move.called
    move.side_effect=ValueError('process identity changed')
    result=api.running_windows('place',{'windows':[rows[0]],'rects':{'1:10':[1920,0,960,570]}})
    assert result['ok'] and not result['data']['results'][0]['ok']
print('PASS: cached verified inventory avoids repeated process scans; native identity failures still reject movement.')
