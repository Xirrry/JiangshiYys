"""Local-only SOCKS5 fixtures; no real proxy credentials or game traffic."""
import copy
import json
from pathlib import Path
import socket
import struct
import threading
import time
from unittest.mock import patch
import proxy_support as p

root = Path(__file__).resolve().parent / 'test-results' / f'proxy-{time.time_ns()}'
store = p.ProxyStore(root)
username, password = 'fixture-login', 'fixture-password-only'
key = store.save({'name': '测试代理', 'host': '127.0.0.1', 'port': 1080,
                  'username': username, 'password': password})
raw = store.file.read_text(encoding='utf-8')
assert password not in raw and username not in raw
assert 'credentials' not in json.dumps(store.public())
assert store.spec(key)['password'] == password
store.save({'id': key, 'name': '改名', 'host': '127.0.0.1', 'port': 1080})
assert store.spec(key)['username'] == username
assert p.ProxyStore(root).spec(key)['password'] == password

tcp = socket.socket()
tcp.bind(('127.0.0.1', 0))
tcp.listen()
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('127.0.0.1', 0))
tcp.settimeout(.2)
udp.settimeout(.2)
stop = threading.Event()
controls = []

def serve_udp():
    while not stop.is_set():
        try:
            data, remote = udp.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        # The proxy returns an actual UDP response carrying the matching DNS ID.
        dns = data[10:]
        reply = dns[:2] + b'\x81\x80' + dns[4:]
        udp.sendto(data[:10] + reply, remote)

def client(sock):
    try:
        with sock:
            assert p.exact(sock, 3) == b'\x05\x01\x02'
            sock.sendall(b'\x05\x02')
            assert p.exact(sock, 1) == b'\x01'
            user = p.exact(sock, p.exact(sock, 1)[0]).decode()
            secret = p.exact(sock, p.exact(sock, 1)[0]).decode()
            if user != username or secret != password:
                sock.sendall(b'\x01\x01')
                return
            sock.sendall(b'\x01\x00')
            header = p.exact(sock, 3)
            host = p.address(sock)
            port = struct.unpack('!H', p.exact(sock, 2))[0]
            controls.append((header[1], host, port))
            sock.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01' + struct.pack('!H', udp.getsockname()[1]))
            if header[1] == 1:
                sock.sendall(b'fixture-reply')
            else:
                sock.settimeout(2)
                try:
                    sock.recv(1)
                except socket.timeout:
                    pass
    except (OSError, ValueError):
        pass

def serve_tcp():
    while not stop.is_set():
        try:
            sock, _ = tcp.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=client, args=(sock,), daemon=True).start()

threads = [threading.Thread(target=f, daemon=True) for f in (serve_tcp, serve_udp)]
for thread in threads:
    thread.start()
spec = {'host': '127.0.0.1', 'port': tcp.getsockname()[1], 'username': username, 'password': password}
try:
    sock, _ = p.connect(spec, 'example.test', 443)
    with sock:
        assert p.exact(sock, 13) == b'fixture-reply'
    assert controls[-1] == (1, 'example.test', 443)
    assert p.udp_probe(spec)
    try:
        p.connect({**spec, 'password': 'wrong'}, 'example.test', 443)
        raise AssertionError('bad credentials accepted')
    except p.ProxyError as error:
        assert '认证失败' in str(error)
    with patch.object(p, 'exit_ip', return_value='203.0.113.7'):
        result = p.diagnose(spec)
        assert result['tcp'] and result['udp'] and not result['game_verified']
        assert result['exit_ip'] == '203.0.113.7'
    store.remember(key, result)
    assert store.public()[0]['last_test']['udp']
finally:
    stop.set()
    tcp.close()
    udp.close()
    for thread in threads:
        thread.join(timeout=1)

import test_desktop_api as fixture
api = fixture.api
proxy_id = api.command('proxy_save', {'name': '绑定测试', 'host': '127.0.0.1', 'port': 1080,
                                     'username': username, 'password': password})['data']
before_plans = copy.deepcopy(api.snapshot()['config']['layout_plans'])
assert api.command('proxy_bind', {'ids': ['a'], 'proxy_id': proxy_id})['ok']
assert next(a for a in api.snapshot()['config']['accounts'] if a['id'] == 'a')['proxy_id'] == proxy_id
assert password not in json.dumps(api.snapshot()) and username not in json.dumps(api.snapshot())
api._app.find_game = lambda *_: (_ for _ in ()).throw(AssertionError('launch path reached'))
with patch.object(Path, 'is_file', return_value=False):
    for action, payload in [('start', {'ids': ['a']}), ('single_start', {'id': 'a'})]:
        result = api.command(action, payload)
        assert not result['ok'] and '未回退直连' in result['error']
    api._layout = lambda _: None
    result = api.command('start_member', {'id': 'a', 'ids': ['a']})
    assert not result['ok'] and '未回退直连' in result['error']
assert api.snapshot()['config']['layout_plans'] == before_plans
assert api.command('proxy_bind', {'ids': ['a'], 'proxy_id': ''})['ok']
api._running = lambda _: True
assert not api.command('proxy_bind', {'ids': ['a'], 'proxy_id': proxy_id})['ok']
print('PASS: DPAPI credential roundtrip/redaction, authenticated SOCKS5 TCP, real local UDP roundtrip, rejected bad auth, unverified-game label, role binding, all launch paths blocked when components missing, running-role guard; schemes unchanged. No external connections or games.')
