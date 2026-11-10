"""Documented LaoYu Pro loopback API. No global rules or parent-tree operations."""
import json
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import urllib.request
import urllib.parse

class LaoYuError(ValueError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise LaoYuError('老鱼 API 返回了重定向，已拒绝')
@contextmanager
def line_lock(port):
    k=C.WinDLL('kernel32',use_last_error=True)
    k.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR];k.CreateMutexW.restype=W.HANDLE
    k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
    k.ReleaseMutex.argtypes=[W.HANDLE];k.CloseHandle.argtypes=[W.HANDLE]
    handle=k.CreateMutexW(None,False,'Local\\YysLaoYuLineSync-'+str(port))
    if not handle:raise LaoYuError('无法建立老鱼线路同步锁')
    acquired=False
    try:
        acquired=k.WaitForSingleObject(handle,20000) in (0,0x80)
        if not acquired:raise LaoYuError('老鱼线路正在同步，请稍后重试')
        yield
    finally:
        if acquired:k.ReleaseMutex(handle)
        k.CloseHandle(handle)

class Client:
    def __init__(self,port=22999):
        self.port=int(port)
        if not 1<=self.port<=65535:raise LaoYuError('老鱼 API 端口无效')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def call(self,path,params=None):
        allowed={'GetLineList','GetProxyList','AddProxyLine','ProcessProxy'}
        if path not in allowed:raise LaoYuError('不支持的老鱼接口')
        url=f'http://127.0.0.1:{self.port}/{path}'
        if params:url+='?'+urllib.parse.urlencode(params,encoding='utf-8')
        try:
            with self.opener.open(url,timeout=4) as response:
                raw=response.read(1048577)
            if len(raw)>1048576:raise LaoYuError('老鱼 API 响应过大')
            data=json.loads(raw.decode('utf-8-sig'))
        except LaoYuError:raise
        except Exception:raise LaoYuError('无法读取老鱼专业版 API，请启动软件并确认本机 API 端口') from None
        if not isinstance(data,dict) or type(data.get('Code')) is not int or data['Code']!=1:
            # API errors may contain proxy authentication details: never echo raw Msg/URL.
            raise LaoYuError('老鱼拒绝了请求，请检查线路或软件设置')
        return data.get('Data')
    def lines(self):
        data=self.call('GetLineList')
        if data is None:return []
        if not isinstance(data,list) or any(not isinstance(x,dict) for x in data):raise LaoYuError('老鱼线路格式不支持')
        return data
    def processes(self):
        data=self.call('GetProxyList')
        if data is None:return []
        if not isinstance(data,list) or any(not isinstance(x,dict) for x in data):raise LaoYuError('老鱼进程格式不支持')
        return data
    @staticmethod
    def matches(line,spec):
        return (str(line.get('ip','')).lower()==str(spec['host']).lower() and
                str(line.get('port'))==str(spec['port']) and line.get('type')==1 and
                str(line.get('user') or '')==str(spec.get('username') or '') and
                str(line.get('password') or '')==str(spec.get('password') or ''))
    def ensure_line(self,spec):
        with line_lock(self.port):
            return self._ensure_line(spec)
    def _ensure_line(self,spec):
        rows=self.lines()
        if spec.get('laoyu_sign') and spec.get('laoyu_port')==self.port:
            exact=next((x for x in rows if x.get('sign')==spec['laoyu_sign']),None)
            if exact and self.matches(exact,spec) and not exact.get('ban'):
                return exact['sign']
            if spec.get('laoyu_managed'):
                raise LaoYuError('老鱼线路已变化或停用，请刷新老鱼线路后重试')
        elif spec.get('laoyu_managed'):
            raise LaoYuError('老鱼 API 端口已变化，请先刷新线路')
        match=next((x for x in rows if self.matches(x,spec)),None)
        if match:
            if match.get('ban'):raise LaoYuError('匹配的老鱼线路已停用，请在老鱼中启用')
            if not match.get('sign'):raise LaoYuError('老鱼线路缺少标识')
            return match['sign']
        self.call('AddProxyLine',{'sign':'','ip':spec['host'],'port':spec['port'],
                   'user':spec.get('username',''),'password':spec.get('password',''),'type':1})
        match=next((x for x in self.lines() if self.matches(x,spec) and not x.get('ban')),None)
        if not match or not match.get('sign'):raise LaoYuError('代理已提交，但未能确认老鱼线路；已阻止游戏启动')
        return match['sign']
    def bound(self,pid,sign):
        return any(isinstance(x.get('Process'),dict) and x['Process'].get('PID')==pid and
                   x.get('lineSign')==sign for x in self.processes())
    def bind(self,pid,sign):
        if type(pid) is not int or pid<=0 or not isinstance(sign,str) or not sign.strip():
            raise LaoYuError('必须明确指定游戏 PID 和线路')
        self.call('ProcessProxy',{'pid':pid,'sign':sign,'ProxySubprocess':1,'ChildProcess':1,'ChildProcessEx':1})
        if not self.bound(pid,sign):raise LaoYuError('老鱼未确认指定 PID 的线路，已阻止游戏运行')
