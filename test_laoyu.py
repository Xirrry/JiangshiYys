"""Local fake API contract tests; no real LaoYu changes, game, or driver."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import threading
from unittest.mock import Mock,patch
import laoyu_support as ly
state={'lines':[],'processes':[],'adds':0,'wrong':False,'error':False,'redirect':False,'requests':[]}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        url=urlparse(self.path);q={k:v[0] for k,v in parse_qs(url.query,keep_blank_values=True).items()}
        state['requests'].append(url.path)
        if state['redirect']:
            self.send_response(302);self.send_header('Location','http://example.invalid/');self.end_headers();return
        if state['error']:data={'Code':0,'Msg':'fixture-secret-password'}
        else:
            result=None
            if url.path=='/GetLineList':result=state['lines']
            elif url.path=='/GetProxyList':result=state['processes'] or None
            elif url.path=='/AddProxyLine':
                assert q['type']=='1'
                state['adds']+=1
                state['lines'].append({'sign':'fixture-line','ip':q['ip'],'port':int(q['port']),'user':q['user'],'password':q['password'],'type':1,'ban':False})
                result='fixture-line'
            elif url.path=='/ProcessProxy':
                assert q['ProxySubprocess']==q['ChildProcess']==q['ChildProcessEx']=='1'
                state['processes']=[{'lineSign':'wrong' if state['wrong'] else q['sign'],'Process':{'PID':int(q['pid'])}}]
            else:raise AssertionError('unexpected API mutation')
            data={'Code':1,'Msg':'ok','Data':result}
        body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
client=ly.Client(server.server_port)
spec={'host':'fixture.invalid','port':1080,'username':'user&中文','password':'secret&=+中文'}
try:
    assert client.ensure_line(spec)=='fixture-line'
    assert client.ensure_line(spec)=='fixture-line' and state['adds']==1
    assert state['lines'][0]['user']==spec['username'] and state['lines'][0]['password']==spec['password']
    client.bind(12345,'fixture-line');assert client.bound(12345,'fixture-line')
    state['wrong']=True
    try:client.bind(12345,'fixture-line')
    except ly.LaoYuError:pass
    else:raise AssertionError('wrong PID-line confirmation accepted')
    for sign in ('',' '):
        try:client.bind(12345,sign)
        except ly.LaoYuError:pass
        else:raise AssertionError('implicit/default route accepted')
    state['error']=True
    try:client.lines()
    except ly.LaoYuError as e:assert 'fixture-secret' not in str(e)
    state['error']=False;state['redirect']=True
    try:client.lines()
    except ly.LaoYuError:pass
    else:raise AssertionError('redirect accepted')
finally:server.shutdown();server.server_close()
import test_desktop_api as fixture
import desktop_api
api=fixture.api
key=api._proxies.save({'name':'fixture','host':'127.0.0.1','port':1080})
assert api.command('proxy_backend',{'backend':'laoyu','port':22999})['ok']
assert api.command('proxy_bind',{'ids':['a','b'],'proxy_id':key})['ok']
assert api.command('launch_preflight',{'ids':['a','b']})['ok']
api._app.find_game=Mock(return_value=(__import__('pathlib').Path('D:/fake'),__import__('pathlib').Path('D:/fake/game.exe')))
api._laoyu_start=Mock(return_value='e'*32);api._app.launch=Mock()
with patch.object(desktop_api.threading,'Thread'):
    result=api.command('start',{'ids':['a','b']})
assert result['ok'],result
assert api._laoyu_start.call_count==2
api._app.launch.assert_not_called()
api._laoyu_states=Mock(return_value={'a':{'active':True,'role_id':'a','provider':'laoyu','ticket':'e'*32}})
assert not api.command('proxy_backend',{'backend':'builtin','port':22999})['ok']
assert not api.command('proxy_bind',{'ids':['a'],'proxy_id':''})['ok']
with patch.object(__import__('pathlib').Path,'write_text') as write:
    assert api.command('close',{'ids':['a'],'force':True})['data']==1
    write.assert_called_once_with('cancel',encoding='ascii')
print('PASS: local LaoYu API encoding/auth preservation; existing-line reuse; exact PID-line confirmation; error redaction; redirect refusal; Pro multi-role dispatch; no direct launch; backend/binding guards; per-role cancellation. No real LaoYu mutations, game or driver.')
