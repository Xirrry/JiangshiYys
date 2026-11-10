import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import re,secrets,uuid
class Module(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('module_id', W.DWORD), ('process_id', W.DWORD), ('global_count', W.DWORD), ('process_count', W.DWORD), ('base', C.c_void_p), ('size', W.DWORD), ('handle', W.HMODULE), ('name', W.WCHAR * 256), ('path', W.WCHAR * 260)]

class Context(C.Structure):
    _fields_ = [('magic', W.DWORD), ('pid', W.DWORD), ('stamp', C.c_ulonglong), ('mutex_name', W.WCHAR * 160), ('name', W.WCHAR * 16), ('serial', W.DWORD), ('mac', C.c_ubyte * 6), ('counters', W.DWORD * 4), ('active', W.DWORD)]

def kernel():
    k = C.WinDLL('kernel32', use_last_error=True)
    signatures = {'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE), 'CloseHandle': ([W.HANDLE], W.BOOL), 'CreateToolhelp32Snapshot': ([W.DWORD, W.DWORD], W.HANDLE), 'Module32FirstW': ([W.HANDLE, C.POINTER(Module)], W.BOOL), 'Module32NextW': ([W.HANDLE, C.POINTER(Module)], W.BOOL), 'VirtualAllocEx': ([W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, W.DWORD], C.c_void_p), 'VirtualFreeEx': ([W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD], W.BOOL), 'WriteProcessMemory': ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL), 'ReadProcessMemory': ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL), 'CreateRemoteThread': ([W.HANDLE, C.c_void_p, C.c_size_t, C.c_void_p, C.c_void_p, W.DWORD, C.c_void_p], W.HANDLE), 'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD), 'GetExitCodeThread': ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL), 'GetModuleHandleExW': ([W.DWORD, C.c_void_p, C.POINTER(W.HMODULE)], W.BOOL), 'GetModuleFileNameW': ([W.HMODULE, W.LPWSTR, W.DWORD], W.DWORD), 'CreateMutexW': ([C.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE)}
    for name, (args, result) in signatures.items():
        getattr(k, name).argtypes = args
        getattr(k, name).restype = result
    return k

def modules(k, pid):
    handle = k.CreateToolhelp32Snapshot(24, pid)
    if handle in (None, C.c_void_p(-1).value):
        raise C.WinError(C.get_last_error())
    result = []
    try:
        entry = Module()
        entry.dwSize = C.sizeof(entry)
        ok = k.Module32FirstW(handle, C.byref(entry))
        while ok:
            result.append((entry.name, str(entry.path), entry.base))
            ok = k.Module32NextW(handle, C.byref(entry))
    finally:
        k.CloseHandle(handle)
    return result

def new_profile():
    seed=secrets.token_bytes(16)
    return {'enabled':False,'computer_name':'YYS-'+seed.hex()[:10].upper(),'volume_serial':int.from_bytes(seed[:4],'little') or 1,'mac':':'.join(f'{b:02X}' for b in bytes([2])+seed[4:9])}

def normalize(value):
    if value is None:return None
    if not isinstance(value,dict) or type(value.get('enabled')) is not bool:raise ValueError('设备实验配置格式无效')
    name=value.get('computer_name','');serial=value.get('volume_serial');mac=value.get('mac','')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,14}',name):raise ValueError('设备名称需为1～15位大写字母、数字或横线')
    if type(serial) is not int or not 1<=serial<=0xffffffff:raise ValueError('卷序列号格式无效')
    if not isinstance(mac,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',mac):raise ValueError('MAC 参数格式无效')
    raw=bytes.fromhex(mac.replace(':',''))
    if raw[0]&3!=2:raise ValueError('实验 MAC 必须是本地管理的单播地址')
    return {'enabled':value['enabled'],'computer_name':name,'volume_serial':serial,'mac':mac.upper()}

class Session:
    def __init__(self,root,state,profile,stamp_fn):
        self.pid=state['pid'];self.stamp=state['stamp'];self.stamp_fn=stamp_fn
        self.k=kernel();self.handle=None;self.gate=None;self.remote=None
        def owned():
            if stamp_fn(self.pid)!=self.stamp:raise ValueError('设备实验目标进程已变化')
        self.owned=owned
        try:
            owned();loaded=modules(self.k,self.pid)
            self.handle=self.k.OpenProcess(0x10043a,False,self.pid)
            if not self.handle:raise C.WinError(C.get_last_error())
            mutex='Local\\YysOwnedHardware-'+str(self.pid)+'-'+uuid.uuid4().hex
            self.gate=self.k.CreateMutexW(None,False,mutex)
            if not self.gate:raise C.WinError(C.get_last_error())
            address=C.cast(self.k.LoadLibraryW,C.c_void_p).value;owner=W.HMODULE()
            if not self.k.GetModuleHandleExW(6,address,C.byref(owner)):raise C.WinError(C.get_last_error())
            owner_path=C.create_unicode_buffer(32768);self.k.GetModuleFileNameW(owner,owner_path,32768)
            remote_owner=next(base for name,_,base in loaded if name.lower()==Path(owner_path.value).name.lower())
            dll=Path(root)/'hardware/IdentityView.dll';path=C.create_unicode_buffer(str(dll))
            pointer=self.allocate(path);self.call(remote_owner+address-owner.value,pointer)
            self.k.VirtualFreeEx(self.handle,pointer,0,0x8000)
            remote_base=next(base for _,path,base in modules(self.k,self.pid) if Path(path).resolve()==dll.resolve())
            self.local=C.WinDLL(str(dll));self.base=remote_base
            ctx=Context();ctx.magic=0x59595331;ctx.pid=self.pid;ctx.stamp=self.stamp;ctx.mutex_name=mutex
            ctx.name=profile['computer_name'];ctx.serial=profile['volume_serial'];ctx.mac[:]=bytes.fromhex(profile['mac'].replace(':',''))
            self.remote=self.allocate(ctx)
            result=self.call(self.export('StartOwnedGameTest'),self.remote)
            if result:raise ValueError('设备实验初始化失败：'+str(result))
        except Exception:
            self.release_handles();raise
    def export(self,name):return self.base+C.cast(getattr(self.local,name),C.c_void_p).value-self.local._handle
    def allocate(self,buffer):
        self.owned();address=self.k.VirtualAllocEx(self.handle,None,C.sizeof(buffer),0x3000,4)
        if not address:raise C.WinError(C.get_last_error())
        written=C.c_size_t()
        if not self.k.WriteProcessMemory(self.handle,address,C.byref(buffer),C.sizeof(buffer),C.byref(written)) or written.value!=C.sizeof(buffer):raise C.WinError(C.get_last_error())
        return address
    def call(self,address,param):
        self.owned();thread=self.k.CreateRemoteThread(self.handle,None,0,address,param,0,None)
        if not thread:raise C.WinError(C.get_last_error())
        try:
            if self.k.WaitForSingleObject(thread,15000)!=0:raise ValueError('设备实验组件响应超时')
            result=W.DWORD();self.k.GetExitCodeThread(thread,C.byref(result));return result.value
        finally:self.k.CloseHandle(thread)
    def read_status(self):
        result=self.call(self.export('OwnedGameTestStatus'),self.remote)
        if result:raise ValueError('设备实验状态读取失败：'+str(result))
        ctx=Context();read=C.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,self.remote,C.byref(ctx),C.sizeof(ctx),C.byref(read)) or read.value!=C.sizeof(ctx):raise C.WinError(C.get_last_error())
        return {'active':bool(ctx.active),'api_calls':list(ctx.counters),'pid':self.pid,'stamp':self.stamp}

    def process_ended(self):
        # A retained process handle is authoritative; query-denied is not exit.
        if not self.handle:return True
        return self.k.WaitForSingleObject(self.handle,0)==0

    def release_handles(self):
        if self.gate:self.k.CloseHandle(self.gate);self.gate=None
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None
