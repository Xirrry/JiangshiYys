"""PID-bound one-shot mail reader; no game action or background polling."""
import ctypes as c
from ctypes import wintypes as w
import threading,uuid,json
from pathlib import Path

def read(pid, expected_stamp, stamp_fn, dll):
    if not expected_stamp or stamp_fn(pid)!=expected_stamp:
        raise ValueError('游戏窗口已变化，请刷新后重试')
    dll=Path(dll).resolve()
    if not dll.is_file():raise ValueError('邮件读取组件不存在')
    k=c.WinDLL('kernel32',use_last_error=True)
    def api(name,restype,*args):
     f=getattr(k,name);f.restype=restype;f.argtypes=list(args);return f
    OpenProcess=api('OpenProcess',w.HANDLE,w.DWORD,w.BOOL,w.DWORD)
    Close=api('CloseHandle',w.BOOL,w.HANDLE)
    Query=api('QueryFullProcessImageNameW',w.BOOL,w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD))
    Alloc=api('VirtualAllocEx',c.c_void_p,w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD,w.DWORD)
    Free=api('VirtualFreeEx',w.BOOL,w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD)
    Write=api('WriteProcessMemory',w.BOOL,w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t))
    Thread=api('CreateRemoteThread',w.HANDLE,w.HANDLE,c.c_void_p,c.c_size_t,c.c_void_p,c.c_void_p,w.DWORD,c.c_void_p)
    Wait=api('WaitForSingleObject',w.DWORD,w.HANDLE,w.DWORD)
    GetModule=api('GetModuleHandleW',w.HMODULE,w.LPCWSTR)
    GetProc=api('GetProcAddress',c.c_void_p,w.HMODULE,c.c_char_p)
    LoadLocal=api('LoadLibraryExW',w.HMODULE,w.LPCWSTR,w.HANDLE,w.DWORD)
    FreeLocal=api('FreeLibrary',w.BOOL,w.HMODULE)
    CreatePipe=api('CreateNamedPipeW',w.HANDLE,w.LPCWSTR,w.DWORD,w.DWORD,w.DWORD,w.DWORD,w.DWORD,w.DWORD,c.c_void_p)
    Connect=api('ConnectNamedPipe',w.BOOL,w.HANDLE,c.c_void_p)
    Read=api('ReadFile',w.BOOL,w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p)
    Snap=api('CreateToolhelp32Snapshot',w.HANDLE,w.DWORD,w.DWORD)
    class MODULE(c.Structure):
     _fields_=[('size',w.DWORD),('id',w.DWORD),('pid',w.DWORD),('global_usage',w.DWORD),('usage',w.DWORD),('base',c.c_void_p),('length',w.DWORD),('module',w.HMODULE),('name',w.WCHAR*256),('path',w.WCHAR*260)]
    First=api('Module32FirstW',w.BOOL,w.HANDLE,c.POINTER(MODULE));Next=api('Module32NextW',w.BOOL,w.HANDLE,c.POINTER(MODULE))
    def modules():
     h=Snap(0x18,pid)
     if h==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
     try:
      row=MODULE();row.size=c.sizeof(row);ok=First(h,c.byref(row));result={}
      while ok:
       result[row.name.lower()]=row.base;ok=Next(h,c.byref(row))
      return result
     finally:Close(h)
    process=OpenProcess(0x43a,False,pid)
    if not process:raise c.WinError(c.get_last_error())
    allocs=[];safe=True;pipe=None
    try:
     path=c.create_unicode_buffer(32768);length=w.DWORD(len(path))
     if not Query(process,0,path,c.byref(length)):raise c.WinError(c.get_last_error())
     if Path(path.value).name.lower() not in {'onmyoji.exe','onmyoji_future.exe'}:raise RuntimeError('Target image mismatch')
     if Wait(process,0)==0:raise RuntimeError('Target exited')
     remote=modules();local=GetModule('kernel32.dll');local_proc=GetProc(local,b'LoadLibraryW')
     # Resolve the actual owning module of LoadLibraryW (forwarded exports may live elsewhere).
     owner=w.HMODULE();GetOwner=api('GetModuleHandleExW',w.BOOL,w.DWORD,c.c_void_p,c.POINTER(w.HMODULE))
     if not GetOwner(6,local_proc,c.byref(owner)):raise c.WinError(c.get_last_error())
     GetName=api('GetModuleFileNameW',w.DWORD,w.HMODULE,w.LPWSTR,w.DWORD);ownerpath=c.create_unicode_buffer(32768);GetName(owner,ownerpath,len(ownerpath));entry=remote[Path(ownerpath.value).name.lower()]+local_proc-owner.value
     def put(data):
      addr=Alloc(process,None,len(data),0x3000,4)
      if not addr:raise c.WinError(c.get_last_error())
      allocs.append(addr);buffer=c.create_string_buffer(data);written=c.c_size_t()
      if not Write(process,addr,buffer,len(data),c.byref(written)) or written.value!=len(data):raise c.WinError(c.get_last_error())
      return addr
     def run(entry,param):
      nonlocal safe
      h=Thread(process,None,0,entry,param,0,None)
      if not h:raise c.WinError(c.get_last_error())
      try:
       if Wait(h,20000)!=0:safe=False;raise RuntimeError('Probe timed out; no game process terminated')
      finally:Close(h)
     run(entry,put((str(dll)+'\0').encode('utf-16le')))
     remote=modules();base=remote.get(dll.name.lower())
     if not base:raise RuntimeError('Probe component did not load')
     localdll=LoadLocal(str(dll),None,1)
     if not localdll:raise c.WinError(c.get_last_error())
     try:
      exported=GetProc(localdll,b'agent_run')
      if not exported:raise RuntimeError('Missing probe entry')
      agent=base+exported-localdll
     finally:FreeLocal(localdll)
     pipename=r'\\.\pipe\yys-mail-pid-'+str(pid)+'-'+uuid.uuid4().hex
     pipe=CreatePipe(pipename,1,0,1,65536,65536,0,None)
     if pipe==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
     payload=[];errors=[]
     def receive():
      try:
       if not Connect(pipe,None) and c.get_last_error()!=535:raise c.WinError(c.get_last_error())
       while True:
        buf=c.create_string_buffer(65536);n=w.DWORD()
        if not Read(pipe,buf,len(buf),c.byref(n),None):
         if c.get_last_error()==109:break
         raise c.WinError(c.get_last_error())
        if not n.value:break
        payload.append(buf.raw[:n.value])
      except Exception as e:errors.append(str(e))
     reader=threading.Thread(target=receive,daemon=True);reader.start()
     run(agent,put(b'\0\0\0\0'+(pipename+'\0').encode('utf-16le')))
     reader.join(5)
     if reader.is_alive():raise RuntimeError('Pipe result incomplete')
     if errors:raise RuntimeError(';'.join(errors))
     result=json.loads(b''.join(payload).decode('utf-8'))
     if stamp_fn(pid)!=expected_stamp:raise RuntimeError('游戏进程已变化，读取结果未保存')
     if result.get('error'):raise ValueError(result['error'])
     return result
    finally:
     if pipe:Close(pipe)
     if safe:
      for addr in allocs:Free(process,addr,0,0x8000)
     Close(process)
