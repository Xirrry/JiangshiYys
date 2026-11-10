"""No external traffic: DNS framing, HTTPS tunnel and native reply validation."""
import ctypes as C
from ctypes import wintypes as W
import io
from pathlib import Path
import struct
import sys
from unittest.mock import Mock,patch
import proxy_dns as dns
import proxy_support
q=b'\x73\x19\x01\x00\x00\x01'+b'\x00'*6+b'\x07example\x03com\x00\x00\x01\x00\x01'
a=q[:2]+b'\x81\x80'+q[4:]
assert dns.validate_reply(q,a)==a
for invalid in (a[:4],b'xx'+a[2:],q,a[:13]+b'changed'+a[20:],a+b'x'*4096):
    try:dns.validate_reply(q,invalid)
    except ValueError:pass
    else:raise AssertionError('invalid DNS reply accepted')
long_answer=a+b'X'*600
truncated=dns.udp_reply(q,long_answer)
assert len(truncated)<=512 and truncated[2]&2 and truncated[6:12]==b'\x00'*6
class TLS:
    def __init__(self,status=200,body=a,ctype='application/dns-message'):
        self.sent=b'';self.response=f'HTTP/1.1 {status} OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n\r\n'.encode()+body
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def sendall(self,data):self.sent+=data
    def makefile(self,*args):return io.BytesIO(self.response)
class Socket:
    def __enter__(self):return self
    def __exit__(self,*args):pass
spec={'host':'fixture','port':1080,'username':'fixture-user','password':'fixture-secret'}
tls=TLS();context=Mock();context.wrap_socket.return_value=tls
with patch.object(proxy_support,'connect',return_value=(Socket(),None)) as connect,patch.object(dns.ssl,'create_default_context',return_value=context):
    assert dns.exchange(spec,q)==a
    connect.assert_called_once_with(spec,'223.5.5.5',443)
    assert tls.sent.endswith(q) and b'POST /dns-query' in tls.sent
    assert spec['password'].encode() not in tls.sent
with patch.object(proxy_support,'connect',side_effect=OSError('fixture')) as connect:
    try:dns.exchange(spec,q)
    except proxy_support.ProxyError:pass
    else:raise AssertionError('failed proxy resolved anyway')
    assert connect.call_count==len(dns.ENDPOINTS)
for status,body,ctype in [(302,a,'application/dns-message'),(200,a,'text/html'),(200,b'xx'+a[2:],'application/dns-message')]:
    context.wrap_socket.return_value=TLS(status,body,ctype)
    with patch.object(proxy_support,'connect',return_value=(Socket(),None)),patch.object(dns.ssl,'create_default_context',return_value=context):
        try:dns.exchange(spec,q)
        except proxy_support.ProxyError:pass
        else:raise AssertionError('invalid HTTP/DNS accepted')
e=Path(__file__).resolve().parent/'proxy-engine-experiment';sys.path.insert(0,str(e))
from game_tcp_trial import load_core
core,_=load_core();core.Yys_BuildDnsReply.argtypes=[C.c_void_p,W.UINT,C.c_void_p,W.UINT,C.c_void_p,W.UINT];core.Yys_BuildDnsReply.restype=W.UINT
ip=struct.pack('!BBHHHBBH4s4s',0x45,0,28+len(q),1,0,64,17,0,b'\x0a\x00\x00\x01',b'\x01\x01\x01\x01')
packet=ip+struct.pack('!HHHH',54321,53,8+len(q),0)+q
out=C.create_string_buffer(600);n=core.Yys_BuildDnsReply(packet,len(packet),a,len(a),out,len(out))
assert n==28+len(a)
reply=out.raw[:n]
assert reply[12:16]==packet[16:20] and reply[16:20]==packet[12:16]
assert struct.unpack('!HH',reply[20:24])==(53,54321) and reply[28:]==a
assert core.Yys_BuildDnsReply(packet,len(packet),b'xx'+a[2:],len(a),out,len(out))==0
assert core.Yys_BuildDnsReply(packet,len(packet),a,len(a),out,20)==0
print('PASS: explicit SOCKS5 HTTPS only; matching DNS question/ID; malformed, oversize, redirect and wrong-type rejection; UDP truncation; no direct fallback; native IP/port reversal and reply bounds. No network or driver.')

import threading
import test_desktop_api as fixture
api=fixture.api
key=api._proxies.save({'name':'dns-fixture','host':'127.0.0.1','port':1080})
assert not api.command('proxy_dns_test',{'id':'missing'})['ok']
entered=threading.Event();release=threading.Event();results=[]
def probe(_):
    entered.set();assert release.wait(3);return {'ok':True,'local_dns_fallback':False}
with patch.object(dns,'probe',side_effect=probe):
    t=threading.Thread(target=lambda:results.append(api.command('proxy_dns_test',{'id':key})));t.start()
    assert entered.wait(1)
    try:assert api.snapshot()['config']['accounts']
    finally:release.set();t.join(2)
assert not t.is_alive() and results[0]['ok']
assert not results[0]['data']['system_dns_verified'] and not results[0]['data']['process_capture_verified']
print('PASS: DNS API rejects missing proxy, keeps snapshot responsive during lookup and never labels game/system DNS verified.')
