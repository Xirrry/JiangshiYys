from pathlib import Path
from unittest.mock import patch,MagicMock
import time,random,copy
import desktop_api,window_groups as G,window_layout as L

plans={'A':{'roles':['a','b']},'B':{'roles':['b','c']}}
groups=[('A',[{'id':'a'},{'id':'b'}]),('B',[{'id':'c'}])]
opts=dict(columns=3,width=320,height=180,gap=8,padding=8)
work=(-1280,-720,1280,720)
rects=G.plan_blocks(groups,work,**opts);assert list(rects)==['a','b','c'];assert rects['c'][1]>rects['b'][1]
flat=G.plan_blocks(groups,work,new_row=False,**opts);assert flat['c'][1]==flat['a'][1]
for i,r in enumerate(rects.values()):
 assert r[0]>=work[0] and r[1]>=work[1] and r[0]+r[2]<=0 and r[1]+r[3]<=0
 assert not any(G.overlaps(r,s) for s in list(rects.values())[i+1:])
# No hidden shrink; an explicit choice can shrink only newly allocated windows.
small=(0,0,800,480)
try:G.plan_blocks(groups,small,width=960,height=540);raise AssertionError('expected full-size refusal')
except G.LayoutSpaceError:pass
assert len(G.plan_blocks(groups,small,width=960,height=540,shrink=True))==3
random.seed(9)
for _ in range(70):
 batch=[('A',[{'id':str(i)} for i in range(random.randint(1,7))]),('B',[{'id':'z'+str(i)} for i in range(random.randint(1,7))])]
 try:
  positions=G.plan_blocks(batch,(0,0,1920,1080),columns=random.randint(1,5),shrink=True)
  values=list(positions.values());assert all(not G.overlaps(a,b) for i,a in enumerate(values) for b in values[i+1:])
 except G.LayoutSpaceError:pass
assert G.plan_blocks([('A',[{'id':'x'}])],(0,0,1920,1080),width=400,height=300,aspect=False)['x'][2:]==[400,300]
print('PASS: scheme/member order, dedup, scheme row boundary, negative monitors, no overlap, immutable obstacles and explicit shrink')

api=desktop_api.DesktopApi(Path(__file__).resolve().parent/'test-results'/('scheme-layout-'+str(time.time_ns())))
cfg={'accounts':[{'id':k,'confirmed':True} for k in 'abc'],'pending':[],'layout_plans':plans,'plan_order':['A','B'],'unified_layout':{**opts,'enabled':True,'screen':'screen'}}
states={'a':{'pid':1,'stamp':10},'b':{'pid':2,'stamp':20},'c':{}}
rows=[{'id':'2:20','pid':2,'stamp':'20','title':'B','rect':[336,8,320,212]},{'id':'1:10','pid':1,'stamp':'10','title':'A','rect':[8,8,320,212]}]
screens=[{'id':'screen','work':[0,0,1280,900],'primary':True}]
u=MagicMock();u.IsIconic.return_value=0;u.IsZoomed.return_value=0
with patch.object(api,'_config',return_value=cfg),patch.object(api,'_save') as save,patch.object(api,'_state',side_effect=lambda k:states.get(k,{})),patch.object(api,'_running',side_effect=lambda s:bool(s.get('pid'))),patch.object(desktop_api.role_reader,'game_pids',return_value=[1,2]),patch.object(L,'running_game_windows',side_effect=lambda *a:copy.deepcopy(rows)),patch.object(L,'screens',return_value=screens),patch.object(L,'border',return_value=(0,32)),patch.object(L,'guarded_window',return_value=100),patch.object(L,'api',return_value=u),patch.object(L,'act',return_value=[0,0,320,212]) as act:
 listing=api.running_windows()['data']['windows'];assert [r['pid'] for r in listing]==[1,2];assert listing[0]['plan']=='A'
 color=listing[0]['plan_color'];assert api._ordered_windows([rows[1]])[0]['plan_color']==color
 preview=api.scheme_layout('preview');assert preview['ok'] and not act.called
 applied=api.scheme_layout('apply');assert applied['ok'];assert [c.args[0]['pid'] for c in act.call_args_list]==[1,2]
 # A disconnected monitor blocks mutation and never falls back to a random screen.
 cfg['unified_layout']['screen']='missing';act.reset_mock();assert not api.scheme_layout('apply')['ok'] and not act.called
 cfg['unified_layout']['screen']='screen';cfg['unified_layout'].update(width=960,height=540)
 rows[:]=[{'id':str(i)+':'+str(i*10),'pid':i,'stamp':str(i*10),'rect':[0,0,960,570]} for i in range(1,5)]
 # Untracked windows are included after schemes and deduplicated once.
 before=api.scheme_layout('preview');assert before['ok'] and before['data']['shrink'];assert not api.scheme_layout('apply')['ok'] and not act.called
 assert api.scheme_layout('apply',{'allow_shrink':True})['ok'] and act.call_count==4
print('PASS: ordered colored inventory, read-only preflight, only new PID moved, shared-role dedup, missing screen refusal and shrink consent')

# Previously saved enabled=True must never override normal startup again.
with patch.object(api,'_config',return_value={'unified_layout':{'enabled':True}}),patch.object(api,'_roles',return_value=[{'id':'a','name':'A','confirmed':True}]),patch.object(api,'_state',return_value={'pid':1,'stamp':10}),patch.object(L,'act') as move,patch.object(api,'_layout',return_value=(['a'],{'a':[8,8,640,360]},[0,0,1920,1080],(0,0))) as local,patch.object(api,'_activate_device'):
    api._launch_status['a']={'phase':'starting','request_id':'request'}
    api._title_later('a',{'request_id':'request','single':True,'ids':['a']})
    local.assert_called_once();assert move.call_args.kwargs['rectangle']==[8,8,640,360]
    assert api._launch_status['a']['phase']=='ready'
    assert 'enabled' not in api._unified_settings({'enabled':True,'shrink_new':True})
assert not hasattr(api,'_prepare_append') and not hasattr(api,'_append_window')
print('PASS: legacy append settings ignored; startup uses the original scheme position; automatic append removed')
