"""Bounded DNS callback workers. No names or credentials written to reports."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading
import proxy_dns

class DnsBridge:
    def __init__(self, core, spec, report):
        self.core,self.spec,self.report=core,spec,report
        self.queue=queue.Queue(maxsize=32);self.stop=threading.Event()
        self.lock=threading.Lock()
        report.update(dns_queries=0,dns_proxied=0,dns_failed=0,dns_process_owned_only=True)
        self.callback_type=C.CFUNCTYPE(None,C.c_uint64,W.DWORD,C.POINTER(C.c_ubyte),W.UINT)
        core.Yys_SetDnsCallback.argtypes=[self.callback_type]
        core.Yys_CompleteDns.argtypes=[C.c_uint64,C.c_void_p,W.UINT]
        core.Yys_CompleteDns.restype=W.BOOL
        core.Yys_ClearDns.argtypes=[]
        self.callback=self.callback_type(self.submit)
        core.Yys_SetDnsCallback(self.callback)
        self.threads=[threading.Thread(target=self.work,daemon=True) for _ in range(2)]
        for t in self.threads:t.start()
    def bump(self,key):
        with self.lock:self.report[key]+=1
    def submit(self,token,pid,data,length):
        self.bump('dns_queries')
        try:
            if self.stop.is_set():raise queue.Full()
            self.queue.put_nowait((token,C.string_at(data,length)))
        except queue.Full:
            self.core.Yys_CompleteDns(token,None,0);self.bump('dns_failed')
    def work(self):
        while not self.stop.is_set():
            try:token,query=self.queue.get(timeout=.2)
            except queue.Empty:continue
            try:
                reply=proxy_dns.udp_reply(query,proxy_dns.exchange(self.spec,query))
                if self.stop.is_set() or not self.core.Yys_CompleteDns(token,reply,len(reply)):
                    self.bump('dns_failed')
                else:self.bump('dns_proxied')
            except Exception:
                self.core.Yys_CompleteDns(token,None,0);self.bump('dns_failed')
            finally:self.queue.task_done()
    def close(self):
        self.stop.set()
        self.core.Yys_SetDnsCallback(self.callback_type())
        self.core.Yys_ClearDns()
        for t in self.threads:t.join(timeout=.3)
