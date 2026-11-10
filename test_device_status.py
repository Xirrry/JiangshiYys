from pathlib import Path
from unittest.mock import Mock,patch
import threading,time
import desktop_api,device_identity
root=Path(__file__).resolve().parent/'test-results'/('device-status-'+str(time.time_ns()));(root/'data').mkdir(parents=True)
api=desktop_api.DesktopApi(root);profile=device_identity.new_profile();profile['enabled']=True
api._save({'accounts':[{'id':'a','confirmed':True,'device_identity':profile}],'pending':[]})
state={'pid':123,'stamp':456};session=Mock(pid=123,stamp=456);session.process_ended.return_value=False
session.read_status.return_value={'active':True,'api_calls':[1,2,3,4]}
with patch.object(api,'_state',side_effect=lambda key:dict(state)),patch.object(api,'_running',return_value=True):
    assert api.command('device_check',{'id':'a'})['data']['phase']=='unverified'
    assert api.command('device_check',{'id':'a'})['data']['hint']
    api._device_sessions['a']=session
    assert api.snapshot()['devices']['a']['phase']=='loaded'
    session.read_status.assert_not_called() # snapshot must not inject diagnostic threads
    result=api.command('device_check',{'id':'a'})['data'];assert result['phase']=='checked' and result['api_calls']==[1,2,3,4] and result['checked_at']>0 and result['stamp']=='456'
    session.read_status.return_value={'active':False,'api_calls':[0,0,0,0]}
    assert api.command('device_check',{'id':'a'})['data']['phase']=='component_inactive'
    session.read_status.side_effect=OSError('fixture access denied')
    assert api.command('device_check',{'id':'a'})['data']['phase']=='check_failed'
    def unlocked_read():
        acquired=[]
        def worker():
            ok=api._lock.acquire(timeout=.3);acquired.append(ok)
            if ok:api._lock.release()
        thread=threading.Thread(target=worker);thread.start();thread.join(1)
        assert acquired==[True]
        return {'active':True,'api_calls':[1,2,3,4]}
    session.read_status.side_effect=unlocked_read
    assert api.command('device_check',{'id':'a'})['data']['phase']=='checked'
    def replaced_read():state['pid']=999;return {'active':True,'api_calls':[1,2,3,4]}
    session.read_status.side_effect=replaced_read
    result=api.command('device_check',{'id':'a'})['data'];assert result['phase']=='unverified' and 'api_calls' not in result
    state['pid']=123
    def reused_pid_read():state['stamp']=999;return {'active':True,'api_calls':[1,2,3,4]}
    session.read_status.side_effect=reused_pid_read
    result=api.command('device_check',{'id':'a'})['data'];assert result['phase']=='unverified' and result['stamp']=='999' and 'api_calls' not in result
    state['stamp']=456;session.read_status.side_effect=None;session.process_ended.return_value=True
    assert api.snapshot()['devices']['a']['phase']=='unverified'
    session.release_handles.assert_called_once();assert 'a' not in api._device_sessions
    assert not api.command('device_check',{'id':'unknown'})['ok']
# A retained live handle prevents edits/removal even if a fresh PID query fails.
api._device_sessions['a']=session;session.process_ended.return_value=False
with patch.object(api,'_running',return_value=False):
    assert not api.command('device_profile',{'id':'a'})['ok']
    assert not api.command('role_meta',{'ids':['a'],'device_identity':None})['ok']
    assert not api.command('remove_roles',{'ids':['a']})['ok']
# WAIT_FAILED is unknown, never proof of process exit.
obj=object.__new__(device_identity.Session);obj.handle=1;obj.k=Mock();obj.k.WaitForSingleObject.return_value=0xffffffff
assert obj.process_ended() is False
obj.k.WaitForSingleObject.return_value=0;assert obj.process_ended() is True
print('PASS: loaded vs checked vs unverified states, on-demand counts/time, query outside config lock, stale PID refusal, exited handle cleanup, unknown-permission guards. No game, hardware or user-data changes.')
