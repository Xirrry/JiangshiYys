"""Private Windows job for the one explicitly owned experimental game family."""
import ctypes as C
from ctypes import wintypes as W
import time

class Limits(C.Structure):
    _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),
              ('min_ws',C.c_size_t),('max_ws',C.c_size_t),('active_limit',W.DWORD),
              ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
class Counters(C.Structure):
    _fields_=[('values',C.c_uint64*6)]
class Extended(C.Structure):
    _fields_=[('basic',Limits),('io',Counters),('process_memory',C.c_size_t),
              ('job_memory',C.c_size_t),('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
class Accounting(C.Structure):
    _fields_=[('times',C.c_int64*4),('faults',W.DWORD),('total',W.DWORD),
              ('active',W.DWORD),('terminated',W.DWORD)]

class OwnedJob:
    def __init__(self, name, create=False):
        self.k=C.WinDLL('kernel32',use_last_error=True)
        k=self.k
        k.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR];k.CreateJobObjectW.restype=W.HANDLE
        k.OpenJobObjectW.argtypes=[W.DWORD,W.BOOL,W.LPCWSTR];k.OpenJobObjectW.restype=W.HANDLE
        k.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
        k.QueryInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p]
        k.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
        k.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)]
        k.TerminateJobObject.argtypes=[W.HANDLE,W.UINT]
        k.CloseHandle.argtypes=[W.HANDLE]
        self.handle=k.CreateJobObjectW(None,name) if create else k.OpenJobObjectW(0x4|0x8,False,name)
        if not self.handle: raise C.WinError(C.get_last_error())
        if create:
            if C.get_last_error()==183:
                self.close();raise RuntimeError('Private job already exists')
            info=Extended(); info.basic.flags=0x2000 # KILL_ON_JOB_CLOSE, no breakaway permission
            if not k.SetInformationJobObject(self.handle,9,C.byref(info),C.sizeof(info)):
                error=C.get_last_error();self.close();raise C.WinError(error)
    def assign(self, process):
        if not self.k.AssignProcessToJobObject(self.handle,process):raise C.WinError(C.get_last_error())
    def contains(self, process):
        result=W.BOOL()
        if not self.k.IsProcessInJob(process,self.handle,C.byref(result)):raise C.WinError(C.get_last_error())
        return bool(result.value)
    def count(self):
        info=Accounting()
        if not self.k.QueryInformationJobObject(self.handle,1,C.byref(info),C.sizeof(info),None):raise C.WinError(C.get_last_error())
        return info.active
    def stop_and_wait(self, report, persist):
        if self.count():
            report['owned_family_stop_requested']=bool(self.k.TerminateJobObject(self.handle,1))
        while self.count():
            report['phase']='waiting_owned_family_exit_before_release';persist();time.sleep(.2)
        report['owned_family_exit_confirmed']=True
    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None
