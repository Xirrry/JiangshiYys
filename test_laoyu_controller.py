"""Mock Windows process handles: verify order and cleanup without starting games."""
import json,time,uuid
from pathlib import Path
from unittest.mock import Mock,patch
import laoyu_controller as lc
from laoyu_support import LaoYuError
root=Path(__file__).resolve().parent/'test-results'/('laoyu-controller-'+uuid.uuid4().hex)
(root/'data').mkdir(parents=True)
(root/'data/accounts.json').write_text(json.dumps({'game':'fixture','accounts':[{'id':'a','proxy_id':'p','confirmed':True}]}))
(root/'launcher.pyw').write_text("from pathlib import Path\nimport json\ndef read_json(p,d):\n try:return json.loads(Path(p).read_text())\n except (OSError,ValueError):return d\ndef account_folder(b,k):\n p=Path(b)/k;p.mkdir(parents=True,exist_ok=True);return p\ndef process_stamp(pid):return None\ndef find_game(g):return Path('C:/fixture'),Path('C:/fixture/game.exe')\ndef prepare(b,g,k):return account_folder(b,k),Path('C:/private'),{'APPDATA':'private-fixture'}\ndef write_json(p,d):Path(p).write_text(json.dumps(d))\n",encoding='utf-8')
def case(mode):
    events=[];ticket=uuid.uuid4().hex;client=Mock();client.ensure_line.side_effect=lambda spec:events.append('sync') or 'line'
    def bind(*args):
        events.append('bind')
        if mode=='bindfail':raise LaoYuError('fixture binding rejected')
    client.bind.side_effect=bind
    client.bound.side_effect=LaoYuError('fixture service disconnected')
    job=Mock();job.count.return_value=1;job.assign.side_effect=lambda _:events.append('assign')
    job.stop_and_wait.side_effect=lambda *_:events.append('stop_family');job.close.side_effect=lambda:events.append('close_job')
    k=Mock();k.ResumeThread.side_effect=lambda _:events.append('resume') or 0
    def create(*args):
        assert args[5]&4 and args[6]['APPDATA']=='private-fixture'
        events.append('create_suspended');return 10,20,101,102
    if mode=='cancel':
        d=root/'data/laoyu-sessions';d.mkdir(exist_ok=True);(d/(ticket+'.cancel')).write_text('cancel')
    with patch.object(lc,'ROOT',root),patch.object(lc,'Client',return_value=client),patch.object(lc,'OwnedJob',return_value=job),patch.object(lc,'kernel',return_value=k),patch.object(lc,'stamp',return_value=777),patch.object(lc._winapi,'CreateProcess',side_effect=create),patch.object(lc._winapi,'CloseHandle'),patch.object(lc.proxy_support,'ProxyStore') as store,patch.object(lc,'alive',return_value=mode=='lost'),patch.object(lc,'ensure_owned_exit',side_effect=lambda *_:events.append('stop_main')):
        store.return_value.spec.return_value={'host':'fixture','port':1080,'password':'private-fixture-secret'}
        lc.run('a','p',ticket,22999)
    report=json.loads((root/'data/laoyu-sessions'/(ticket+'.json')).read_text(encoding='utf-8'))
    assert 'private-fixture-secret' not in json.dumps(report)
    if mode=='cancel':assert not events and report['phase']=='cancelled'
    else:
        assert events.index('create_suspended')<events.index('assign')<events.index('bind')
        assert events.index('stop_family')<events.index('stop_main')<events.index('close_job')
        if mode=='bindfail':assert 'resume' not in events and report['phase']=='failed'
        else:
            assert events.index('bind')<events.index('resume')
            assert report['phase']==('failed' if mode=='lost' else 'game_exited')
for mode in ('normal','bindfail','cancel','lost'):case(mode)
print('PASS: private environment; suspended create and job assignment before PID binding; resume only after confirmation; bind failure never resumes; cancellation; service-loss cleanup order; reports omit credentials. No processes or network started.')
