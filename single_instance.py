"""Per-session single instance and activation shared across install directories."""
import atexit
import ctypes
from ctypes import wintypes
import os
import threading
import time

NAME = 'Local\\XiNai.JiangshiYys.Launcher'


class Instance:
    def __init__(self, name=NAME):
        self.name = name
        self.handle = self._event = None
        self._hwnd = None
        self._native = None
        self._thread = None
        self._stop = threading.Event()
        self._lifecycle = threading.RLock()
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for method, args, result in [
            ('CreateMutexW', [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ('CreateEventW', [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetEvent', [wintypes.HANDLE], wintypes.BOOL),
            ('WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ]:
            function = getattr(self.api, method)
            function.argtypes, function.restype = args, result
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self._enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        for method, args, result in [
            ('EnumWindows', [self._enum_callback, wintypes.LPARAM], wintypes.BOOL),
            ('GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            ('GetWindowTextW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ('GetClassNameW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ('SetPropW', [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE], wintypes.BOOL),
            ('GetPropW', [wintypes.HWND, wintypes.LPCWSTR], wintypes.HANDLE),
            ('RemovePropW', [wintypes.HWND, wintypes.LPCWSTR], wintypes.HANDLE),
            ('IsWindow', [wintypes.HWND], wintypes.BOOL),
            ('IsWindowVisible', [wintypes.HWND], wintypes.BOOL),
            ('IsIconic', [wintypes.HWND], wintypes.BOOL),
            ('ShowWindowAsync', [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            ('ShowWindow', [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            ('SetForegroundWindow', [wintypes.HWND], wintypes.BOOL),
            ('AllowSetForegroundWindow', [wintypes.DWORD], wintypes.BOOL),
            ('GetLastActivePopup', [wintypes.HWND], wintypes.HWND),
        ]:
            function = getattr(self.user, method)
            function.argtypes, function.restype = args, result
        # Create the auto-reset event before acquiring the mutex. A rapid second
        # launch can leave a pending request before the first window is ready.
        self._event = self.api.CreateEventW(None, False, False, name + '.Activate')
        if not self._event:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.set_last_error(0)
        self.handle = self.api.CreateMutexW(None, False, name)
        if not self.handle:
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, '无法创建启动器单例锁')
        self.duplicate = ctypes.get_last_error() == 183
        if self.duplicate:
            self.api.CloseHandle(self.handle)
            self.handle = None
        atexit.register(self.close)

    @property
    def window_property(self):
        return self.name + '.Window'

    def _owner(self, hwnd):
        owner = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        return owner.value

    def _find_window(self, legacy_title):
        marked, legacy = [], []

        @self._enum_callback
        def visit(hwnd, unused):
            pid = self._owner(hwnd)
            if pid and self.user.GetPropW(hwnd, self.window_property) == pid:
                marked.append((hwnd, pid, True))
            elif legacy_title:
                title, kind = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(128)
                self.user.GetWindowTextW(hwnd, title, len(title))
                self.user.GetClassNameW(hwnd, kind, len(kind))
                if title.value.startswith(legacy_title + ' · v') and kind.value.startswith('WindowsForms10.Window'):
                    legacy.append((hwnd, pid, False))
            return True

        self.user.EnumWindows(visit, 0)
        return next(iter(marked or legacy), None)

    def _focus_window(self, hwnd, pid, synchronous=False):
        if not self.user.IsWindow(hwnd) or self._owner(hwnd) != pid:
            return False
        show = self.user.ShowWindow if synchronous else self.user.ShowWindowAsync
        if self.user.IsIconic(hwnd):
            show(hwnd, 9)  # Restore the previous normal/maximized state.
        elif not self.user.IsWindowVisible(hwnd):
            show(hwnd, 5)
        popup = self.user.GetLastActivePopup(hwnd)
        if popup and self._owner(popup) == pid and self.user.IsWindowVisible(popup):
            hwnd = popup
        return bool(self.user.SetForegroundWindow(hwnd))

    def activate_existing(self, legacy_title='', timeout=5.0):
        """Notify the first process and transfer foreground permission to it."""
        if self._event:
            self.api.SetEvent(self._event)
        deadline = time.monotonic() + max(0, timeout)
        while True:
            target = self._find_window(legacy_title)
            if target:
                hwnd, pid, managed = target
                self.user.AllowSetForegroundWindow(pid)
                if self._event:
                    self.api.SetEvent(self._event)
                # The owner serializes restore on its UI thread. Restoring from
                # both processes can unmaximize an initially minimized window.
                return True if managed else self._focus_window(hwnd, pid)
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def attach(self, view):
        """Register only the launcher's native top-level window, after it is shown."""
        from System import Action
        with self._lifecycle:
            if self.duplicate or self._hwnd or self._stop.is_set():
                return
            hwnd = int(view.native.Handle.ToInt64())
            if self._owner(hwnd) != os.getpid():
                raise ValueError('单实例窗口不属于当前启动器')
            if not self.user.SetPropW(hwnd, self.window_property, os.getpid()):
                raise ctypes.WinError(ctypes.get_last_error())
            self._hwnd, self._native = hwnd, view.native
            self._activate_action = Action(self._activate_attached)
            self._thread = threading.Thread(target=self._listen, name='launcher-activation', daemon=True)
            self._thread.start()

    def _activate_attached(self):
        with self._lifecycle:
            if not self._stop.is_set() and self._hwnd:
                self._focus_window(self._hwnd, os.getpid(), synchronous=True)

    def _listen(self):
        while not self._stop.is_set():
            result = self.api.WaitForSingleObject(self._event, 250)
            if self._stop.is_set():
                break
            if result == 0:
                with self._lifecycle:
                    if self._stop.is_set():
                        break
                    try:
                        self._native.BeginInvoke(self._activate_action)
                    except Exception:
                        break  # The native window is already closing.
            elif result != 258:  # WAIT_TIMEOUT
                break

    def detach(self):
        """Remove the window marker before destruction, retaining the instance lock."""
        with self._lifecycle:
            self._stop.set()
            if self._event and self._thread:
                self.api.SetEvent(self._event)
            if self._hwnd:
                if self._owner(self._hwnd) == os.getpid():
                    self.user.RemovePropW(self._hwnd, self.window_property)
                self._hwnd = self._native = None
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def close(self):
        self.detach()
        with self._lifecycle:
            # Never close a handle while another thread is still waiting on it.
            if self._event and not (self._thread and self._thread.is_alive()):
                self.api.CloseHandle(self._event)
                self._event = None
            if self.handle:
                self.api.CloseHandle(self.handle)
                self.handle = None
