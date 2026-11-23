from unittest.mock import patch,MagicMock
from pathlib import Path
import time
import window_layout as L,window_groups as G,desktop_api

rows=[{'id':'1:10','pid':1,'stamp':'10'},{'id':'2:20','pid':2,'stamp':'20'},{'id':'3:30','pid':3,'stamp':'30'}]
plans={'A':{'roles':['a','b']},'B':{'roles':['b','a']}}
states={'a':{'pid':1,'stamp':10},'b':{'pid':2,'stamp':20}}
g=G.group_rows(rows,plans,['B','A'],states)
assert [(n,[r['pid'] for r in rs]) for n,rs in g]==[('B',[2,1]),('未归入方案的窗口',[3])]
assert G.group_rows(rows,plans,[],{**states,'a':{'pid':1,'stamp':99}},only='A')==[('A',[rows[1]])]
assert G.group_rows(rows,plans,[],states,only='missing')==[]
for work in [(0,0,1920,1080),(-1920,-1080,1920,1080)]:
 for mode in ['错落排列','反向错落']:
  for calculate in [lambda:L.rectangles(['a','b','c'],work,width=640,height=360,mode=mode),lambda:L.profile_rectangles(['a','b','c'],work,{'b':{'width':800,'height':450}},mode=mode)]:
   rects=calculate();v=list(rects.values());assert v[0][0]<v[1][0]<v[2][0]
   assert (v[0][1]>v[1][1]>v[2][1]) if mode=='反向错落' else (v[0][1]<v[1][1]<v[2][1])
   assert min(r[0] for r in v)>=work[0]+8 and min(r[1] for r in v)>=work[1]+8
   assert all(r[0]>=work[0] and r[1]>=work[1] and r[0]+r[2]<=work[0]+work[2] and r[1]+r[3]<=work[1]+work[3] for r in v)
print('PASS: exact PID/stamp, ordered plans/members, dedup, reverse direction, mixed sizes and negative monitors, inset origins')
api=desktop_api.DesktopApi(Path(__file__).resolve().parent/'test-results'/('groups-'+str(time.time_ns())))
with patch.object(api,'_config',return_value={'layout_plans':plans,'plan_order':['B','A']}),patch.object(api,'_state',side_effect=lambda k:states[k]),patch.object(desktop_api.role_reader,'game_pids',return_value=[1,2,3]),patch.object(L,'running_game_windows',return_value=rows),patch.object(G,'GroupFrames') as constructor:
 manager=constructor.return_value;manager.stopped=False;manager.command.return_value={'visible':True,'groups':2,'error':''}
 assert not api.group_frames()['data']['visible'] and not constructor.called
 assert not api.group_frames('show',{'plan':'missing'})['ok'] and not constructor.called
 assert api.group_frames('show',{'plan':'B'})['ok'];assert manager.command.call_args.args[1]==[('B',[rows[1],rows[0]])]
 api.group_frames('hide');assert manager.command.call_args.args==('hide',)
 api.close_group_frames();manager.close.assert_called_once()
print('PASS: launcher bridge, lazy start, scope validation, explicit show/hide and shutdown')
# Real native event-loop lifecycle with no game changes.
manager=G.GroupFrames(lambda pid:None)
assert manager.status()['visible'] is False
manager.command('show',[]);assert not manager.status()['visible']
manager.command('show',[('测试分组',[{'id':'0:1','pid':0,'stamp':'1'}])]);assert manager.status()['groups']==1
manager.command('show',[])
manager.command('hide');manager.close();assert manager.stopped and not manager.thread.is_alive()
manager.close()
print('PASS: native Tk thread starts hidden and shuts down cleanly without a hotkey')

# Explicit diagonal origin and per-axis offsets replace the old implicit inset.
for mode in ['错落排列','反向错落']:
 r=L.profile_rectangles(['a','b','c'],(-1920,0,1920,1040),{},mode=mode,
                        start_x=50,start_y=60,offset_x=130,offset_y=75)
 assert r['a'][0]==-1920+8+50
 assert min(v[1] for v in r.values())==8+60
 assert r['b'][0]-r['a'][0]==130
 assert r['b'][1]-r['a'][1]==(-75 if mode=='反向错落' else 75)
print('PASS: explicit diagonal origin and exact independent offsets in both directions')
