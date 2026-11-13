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
