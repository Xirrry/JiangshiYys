"""DNS wire messages over TLS through an explicit SOCKS5. Never direct fallback."""
import http.client
import ssl
import struct
import proxy_support

MAX_MESSAGE=4096
ENDPOINTS=(('223.5.5.5','dns.alidns.com'),('1.1.1.1','cloudflare-dns.com'))

def question(message):
    if not 12 <= len(message) <= MAX_MESSAGE:
        raise ValueError('Invalid DNS message length')
    if message[4:6] != b'\x00\x01' or message[2]&0x78:
        raise ValueError('Only standard single-question DNS is supported')
    labels=[];offset=12;size=0
    while True:
        if offset>=len(message):raise ValueError('Truncated DNS question')
        length=message[offset];offset+=1
        if not length:break
        if length>63 or offset+length>len(message):raise ValueError('Invalid DNS label')
        labels.append(message[offset:offset+length].lower());offset+=length;size+=length+1
        if size>254:raise ValueError('DNS name too long')
    if offset+4>len(message):raise ValueError('Truncated DNS question type')
    return (tuple(labels),message[offset:offset+4]),offset+4

def validate_reply(query, reply):
    q,_=question(query);a,_=question(reply)
    if query[2]&0x80 or not reply[2]&0x80 or reply[:2]!=query[:2] or q!=a:
        raise ValueError('DNS response does not match request')
    return reply

def udp_reply(query, reply):
    validate_reply(query,reply)
    # Conservative classic UDP limit: a client may retry a truncated answer via TCP.
    if len(reply)>512:
        _,end=question(query)
        flags=(int.from_bytes(reply[2:4],'big')|0x8200)
        return query[:2]+struct.pack('!H',flags)+b'\x00\x01'+b'\x00'*6+query[12:end]
    return reply

def exchange(spec, query):
    question(query)
    if query[2]&0x80:raise ValueError('A DNS query is required')
    for ip,hostname in ENDPOINTS:
        try:
            sock,_=proxy_support.connect(spec,ip,443)
            with sock:
                with ssl.create_default_context().wrap_socket(sock,server_hostname=hostname) as tls:
                    header=(f'POST /dns-query HTTP/1.1\r\nHost: {hostname}\r\n'
                            f'Content-Type: application/dns-message\r\nAccept: application/dns-message\r\n'
                            f'Content-Length: {len(query)}\r\nConnection: close\r\n\r\n').encode('ascii')
                    tls.sendall(header+query)
                    response=http.client.HTTPResponse(tls);response.begin()
                    if response.status!=200 or response.getheader('Content-Type','').split(';')[0].strip().lower()!='application/dns-message':
                        raise ValueError('Invalid DoH HTTP response')
                    reply=response.read(MAX_MESSAGE+1)
                    validate_reply(query,reply)
                    return reply
        except (OSError,ValueError,http.client.HTTPException,proxy_support.ProxyError):
            continue
    raise proxy_support.ProxyError('DNS 代理解析失败；未回退本地 DNS')

def probe(spec):
    query=b'\x73\x19\x01\x00\x00\x01'+b'\x00'*6+b'\x07example\x03com\x00\x00\x01\x00\x01'
    reply=exchange(spec,query)
    if reply[3]&15 or reply[6:8]==b'\x00\x00':raise proxy_support.ProxyError('DNS 代理未返回有效答案')
    return {'ok':True,'transport':'SOCKS5 + HTTPS','local_dns_fallback':False}
