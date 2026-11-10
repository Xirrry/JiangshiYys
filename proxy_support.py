"""SOCKS5 diagnostics. Does not redirect game traffic or modify system networking."""
import base64
import ctypes as C
from ctypes import wintypes as W
import http.client
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import ssl
import struct
import time
import uuid


class ProxyError(ValueError):
    pass


def protect(data, decrypt=False):
    class Blob(C.Structure):
        _fields_ = [('length', W.DWORD), ('data', C.POINTER(C.c_ubyte))]
    buf = C.create_string_buffer(data)
    source = Blob(len(data), C.cast(buf, C.POINTER(C.c_ubyte)))
    target = Blob()
    crypt = C.WinDLL('crypt32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [C.c_void_p]
    kernel.LocalFree.restype = C.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [C.POINTER(Blob), C.c_void_p, C.c_void_p, C.c_void_p,
                   C.c_void_p, W.DWORD, C.POINTER(Blob)]
    fn.restype = W.BOOL
    if not fn(C.byref(source), None, None, None, None, 1, C.byref(target)):
        raise ProxyError('无法使用当前 Windows 用户的加密凭证')
    try:
        return C.string_at(target.data, target.length)
    finally:
        kernel.LocalFree(target.data)


class ProxyStore:
    def __init__(self, root):
        self.file = Path(root) / 'data/proxies.json'

    def _document(self):
        if not self.file.exists():
            return {'version':1,'proxies':[]}
        return json.loads(self.file.read_text(encoding='utf-8'))

    def records(self):
        return self._document()['proxies']

    def _write(self, rows, ignored=None):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        document = self._document()
        document.update(version=1,proxies=rows)
        if ignored is not None:
            document['ignored_laoyu'] = ignored
        tmp = self.file.with_suffix('.tmp')
        tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.file)

    def remove(self, key):
        rows = self.records()
        old = next((x for x in rows if x['id']==key),None)
        if old is None:
            raise ProxyError('代理已不存在，请刷新后重试')
        ignored = self._document().get('ignored_laoyu',[])
        if old.get('laoyu_sign'):
            entry = {'port':old.get('laoyu_port',22999),'sign':old['laoyu_sign']}
            if entry not in ignored:
                ignored.append(entry)
        self._write([x for x in rows if x['id']!=key],ignored)

    def hidden_laoyu(self, port):
        return sum(x.get('port')==port for x in self._document().get('ignored_laoyu',[]))

    def restore_laoyu(self, port):
        ignored = self._document().get('ignored_laoyu',[])
        count = sum(x.get('port')==port for x in ignored)
        self._write(self.records(),[x for x in ignored if x.get('port')!=port])
        return count

    def public(self):
        return [{k: v for k, v in row.items() if k != 'credentials'} for row in self.records()]

    def save(self, p):
        rows = self.records()
        old = next((r for r in rows if r['id'] == p.get('id')), None)
        if p.get('id') and not old:
            raise ProxyError('代理已不存在，请刷新后重试')
        host = str(p.get('host', '')).strip()
        name = str(p.get('name', '')).strip()
        try:
            port = int(str(p.get('port', '')).strip())
        except ValueError:
            raise ProxyError('端口需为 1～65535 的整数') from None
        if not name or len(name) > 60 or not host or len(host) > 253 or any(c.isspace() for c in host) or any(c in host for c in '/@?#') or not 1 <= port <= 65535:
            raise ProxyError('请填写名称、主机地址和有效端口；地址不要包含协议或密码')
        user, password = str(p.get('username', '')), str(p.get('password', ''))
        if len(user.encode()) > 255 or len(password.encode()) > 255:
            raise ProxyError('用户名或密码超出 SOCKS5 长度限制')
        row = {**(old or {}), 'id': old['id'] if old else uuid.uuid4().hex,
               'name': name, 'host': host, 'port': port, 'enabled': bool(p.get('enabled', True))}
        if old and not old.get('laoyu_managed') and (host!=old.get('host') or port!=old.get('port') or user or password or p.get('clear_auth')):
            for key in list(row):
                if key.startswith('laoyu_'):
                    row.pop(key)
        if p.get('clear_auth'):
            row.pop('credentials', None)
        elif user or password:
            if not user or not password:
                raise ProxyError('用户名和密码需一起填写；编辑时均留空可保留原凭证')
            row['credentials'] = base64.b64encode(protect(json.dumps([user, password]).encode())).decode()
        row['has_auth'] = bool(row.get('credentials'))
        row.pop('last_test', None)
        rows = [r for r in rows if r['id'] != row['id']] + [row]
        self._write(rows)
        return row['id']

    def spec(self, key):
        row = next((r for r in self.records() if r['id'] == key), None)
        if not row or not row.get('enabled'):
            raise ProxyError('绑定的代理不存在或已停用')
        spec = dict(row)
        spec['username'], spec['password'] = ('', '')
        if row.get('credentials'):
            spec['username'], spec['password'] = json.loads(protect(base64.b64decode(row['credentials']), True))
        return spec

    def import_laoyu(self, lines, api_port=22999):
        rows = self.records()
        imported = updated = skipped = 0
        seen = set()
        ignored = {x.get('sign') for x in self._document().get('ignored_laoyu',[]) if x.get('port')==api_port}
        auth_cache = {}
        def auth(row):
            if row['id'] not in auth_cache:
                auth_cache[row['id']] = json.loads(protect(base64.b64decode(row['credentials']), True)) if row.get('credentials') else ['', '']
            return auth_cache[row['id']]
        for index, line in enumerate(lines):
            try:
                sign = str(line.get('sign') or '')
                host = str(line.get('ip') or '').strip()
                port = int(line.get('port', 0))
                user, password = str(line.get('user') or ''), str(line.get('password') or '')
                if (line.get('type') != 1 or not sign or len(sign)>256 or not host or len(host)>253 or
                    any(c.isspace() for c in host) or any(c in host for c in '/@?#') or not 1<=port<=65535 or
                    bool(user)!=bool(password) or len(user.encode())>255 or len(password.encode())>255):
                    raise ValueError('unsupported line')
            except (ValueError, TypeError, AttributeError):
                skipped += 1
                continue
            if sign in seen or sign in ignored:
                continue
            seen.add(sign)
            old = next((x for x in rows if x.get('laoyu_sign')==sign and x.get('laoyu_port')==api_port), None)
            if old is None:
                old = next((x for x in rows if not x.get('laoyu_sign') and x.get('host','').lower()==host.lower() and
                            x.get('port')==port and auth(x)==[user,password]), None)
            new = old is None
            managed = new or bool(old.get('laoyu_managed'))
            row = dict(old or {'id':uuid.uuid4().hex,'name':f'老鱼线路 {index+1}'})
            exit_ip = ''
            try:exit_ip = str(ipaddress.ip_address(line.get('check_ip') or ''))
            except ValueError:pass
            row.update(host=host,port=port,laoyu_sign=sign,laoyu_port=api_port,laoyu_managed=managed,
                       laoyu_missing=False,laoyu_banned=bool(line.get('ban')),laoyu_exit_ip=exit_ip,
                       laoyu_area=str(line.get('check_area') or '')[:120])
            if managed:
                row['enabled'] = not row['laoyu_banned']
            if user:
                row['credentials'] = base64.b64encode(protect(json.dumps([user,password]).encode())).decode()
            else:
                row.pop('credentials', None)
            row['has_auth'] = bool(row.get('credentials'))
            if old and (auth(old)!=[user,password] or old.get('host')!=host or old.get('port')!=port):
                row.pop('last_test',None)
            if old:
                rows[rows.index(old)] = row
                updated += 1
            else:
                rows.append(row)
                imported += 1
        for row in rows:
            if row.get('laoyu_managed') and row.get('laoyu_port')==api_port and row.get('laoyu_sign') not in seen:
                row.update(laoyu_missing=True,enabled=False)
        self._write(rows)
        return {'added':imported,'updated':updated,'skipped':skipped}

    def remember(self, key, result):
        rows = self.records()
        row = next((r for r in rows if r['id'] == key), None)
        if row:
            row['last_test'] = result
            self._write(rows)


def exact(sock, n):
    result = b''
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise ProxyError('代理提前断开连接')
        result += part
    return result


def address(sock):
    kind = exact(sock, 1)[0]
    if kind == 1:
        return socket.inet_ntop(socket.AF_INET, exact(sock, 4))
    if kind == 4:
        return socket.inet_ntop(socket.AF_INET6, exact(sock, 16))
    if kind == 3:
        return exact(sock, exact(sock, 1)[0]).decode('idna')
    raise ProxyError('代理返回无效地址格式')


def connect(spec, host, port, command=1):
    sock = socket.create_connection((spec['host'], spec['port']), timeout=6)
    try:
        sock.settimeout(6)
        auth = bool(spec.get('username'))
        sock.sendall(b'\x05\x01' + (b'\x02' if auth else b'\x00'))
        response = exact(sock, 2)
        if response != (b'\x05\x02' if auth else b'\x05\x00'):
            raise ProxyError('代理不接受当前认证方式')
        if auth:
            user, password = spec['username'].encode(), spec['password'].encode()
            sock.sendall(b'\x01' + bytes([len(user)]) + user + bytes([len(password)]) + password)
            if exact(sock, 2) != b'\x01\x00':
                raise ProxyError('代理用户名或密码认证失败')
        try:
            ip = ipaddress.ip_address(host)
            destination = bytes([1 if ip.version == 4 else 4]) + ip.packed
        except ValueError:
            domain = host.encode('idna')
            if len(domain) > 255:
                raise ProxyError('目标地址过长')
            destination = bytes([3, len(domain)]) + domain
        sock.sendall(bytes([5, command, 0]) + destination + struct.pack('!H', port))
        response = exact(sock, 3)
        if response[0] != 5 or response[2] != 0:
            raise ProxyError('SOCKS5 返回无效响应')
        if response[1] != 0:
            reasons = {1: '代理服务内部失败', 2: '代理规则禁止此目标', 3: '目标网络不可达',
                       4: '目标主机不可达或域名解析失败', 5: '目标端口拒绝连接',
                       6: '连接超时', 7: '不支持此代理命令', 8: '不支持此地址类型'}
            stage = 'TCP CONNECT' if command == 1 else 'UDP ASSOCIATE'
            raise ProxyError(f'{stage} 被拒绝：{reasons.get(response[1], "未知错误")}（0x{response[1]:02X}）')
        bound = address(sock)
        bound_port = struct.unpack('!H', exact(sock, 2))[0]
        return sock, (bound, bound_port)
    except Exception:
        sock.close()
        raise


def exit_ip(spec):
    sock, _ = connect(spec, 'api.ipify.org', 443)
    with sock:
        with ssl.create_default_context().wrap_socket(sock, server_hostname='api.ipify.org') as tls:
            tls.sendall(b'GET /?format=json HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n')
            response = http.client.HTTPResponse(tls)
            response.begin()
            if response.status != 200:
                raise ProxyError('出口 IP 检测服务暂不可用')
            ip = json.loads(response.read(4096))['ip']
            return str(ipaddress.ip_address(ip))


def udp_probe(spec, dns_host='1.1.1.1', associated=None):
    # Announce the actual bound UDP port. Some servers require this instead of
    # accepting the wildcard endpoint permitted by SOCKS5.
    family = socket.getaddrinfo(spec['host'], spec['port'], type=socket.SOCK_STREAM)[0][0]
    wildcard = '::' if family == socket.AF_INET6 else '0.0.0.0'
    with socket.socket(family, socket.SOCK_DGRAM) as udp:
        udp.bind((wildcard, 0))
        control, relay = connect(spec, wildcard, udp.getsockname()[1], command=3)
        with control:
            if associated:
                associated()
            host = spec['host'] if relay[0] in ('0.0.0.0', '::') else relay[0]
            remote = socket.getaddrinfo(host, relay[1], family=family, type=socket.SOCK_DGRAM)[0][4]
            udp.settimeout(4)
            udp.connect(remote)
            transaction = secrets.token_bytes(2)
            query = transaction + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + b'\x07example\x03com\x00\x00\x01\x00\x01'
            udp.send(b'\x00\x00\x00\x01' + socket.inet_aton(dns_host) + struct.pack('!H', 53) + query)
            response = udp.recv(4096)
            if len(response) < 10 or response[:3] != b'\x00\x00\x00':
                raise ProxyError('UDP 返回数据格式无效')
            kind = response[3]
            offset = 10 if kind == 1 else 22 if kind == 4 else 7 + response[4] if kind == 3 else len(response)
            dns = response[offset:]
            if len(dns) < 12 or dns[:2] != transaction or not dns[2] & 128:
                raise ProxyError('UDP 未返回有效 DNS 应答')
            return True


def tcp_probe(spec):
    sock, _ = connect(spec, 'www.baidu.com', 443)
    with sock:
        with ssl.create_default_context().wrap_socket(sock, server_hostname='www.baidu.com') as tls:
            tls.sendall(b'HEAD / HTTP/1.1\r\nHost: www.baidu.com\r\nConnection: close\r\n\r\n')
            reply = http.client.HTTPResponse(tls)
            reply.begin()
            if not 200 <= reply.status < 500:
                raise ProxyError('备用 TCP 目标未返回正常 HTTP 响应')
            return True


def diagnostic_error(error, fallback):
    if isinstance(error, ProxyError):
        return str(error)
    if isinstance(error, (socket.timeout, TimeoutError)):
        return fallback + '：连接超时'
    if isinstance(error, ssl.SSLCertVerificationError):
        return fallback + '：TLS 证书验证失败'
    if isinstance(error, ConnectionRefusedError):
        return fallback + '：连接被拒绝'
    return fallback + '，请检查代理和目标访问权限'


def diagnose(spec):
    result = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'tcp': False, 'udp': False,
              'udp_associate': False, 'exit_ip': '', 'game_verified': False, 'error': '',
              'exit_error': '', 'udp_error': '', 'tcp_target': '', 'udp_target': ''}
    start = time.monotonic()
    try:
        result['exit_ip'] = exit_ip(spec)
        result['tcp'] = True
        result['tcp_target'] = 'api.ipify.org'
        result['latency_ms'] = round((time.monotonic() - start) * 1000)
    except Exception as error:
        result['exit_error'] = diagnostic_error(error, '出口 IP 查询失败')
        try:
            fallback_start = time.monotonic()
            result['tcp'] = tcp_probe(spec)
            result['tcp_target'] = 'www.baidu.com'
            result['latency_ms'] = round((time.monotonic() - fallback_start) * 1000)
        except Exception as second:
            result['error'] = diagnostic_error(second, '备用 TCP 检测失败')
    def associated():
        result['udp_associate'] = True
    for dns_host in ('1.1.1.1', '223.5.5.5'):
        try:
            result['udp'] = udp_probe(spec, dns_host, associated)
            result['udp_target'] = dns_host
            result['udp_error'] = ''
            break
        except Exception as error:
            result['udp_error'] = diagnostic_error(error, 'UDP 数据往返检测失败')
    return result
