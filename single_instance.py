"""Per-login-session named mutex shared across installation directories."""
import ctypes
from ctypes import wintypes
NAME = 'Local\\XiNai.JiangshiYys.Launcher'

class Instance:
    def __init__(self, name=NAME):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        ctypes.set_last_error(0)
        self.handle = self.api.CreateMutexW(None, False, name)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), '无法创建启动器单例锁')
        self.duplicate = ctypes.get_last_error() == 183
        if self.duplicate:
            self.close()

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
