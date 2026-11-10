"""Pure geometry and guarded Windows window operations; no global process closing."""
import ctypes as C
from ctypes import wintypes as W
import math


def rectangles(keys, work, width=640, height=360, columns=3, gap=8, padding=8,
               aspect=True, mode='网格排列', frame=(0, 0)):
    if not keys:
        return {}
    x, y, total_w, total_h = map(int, work)
    width, height, columns, gap, padding = map(int, (width, height, columns, gap, padding))
    if min(width, height, columns, total_w, total_h) <= 0 or min(gap, padding) < 0:
        raise ValueError('尺寸、列数必须大于零，间距和留白不能为负')
    if width < 160 or height < 90:
        raise ValueError('游戏画面尺寸至少为 160 × 90')
    cols = min(columns, len(keys))
    rows = math.ceil(len(keys) / cols)
    fw, fh = frame
    if mode == '错落排列':
        offset = 28
        max_w = total_w - padding * 2 - offset * (len(keys) - 1)
        max_h = total_h - padding * 2 - offset * (len(keys) - 1)
    else:
        max_w = (total_w - padding * 2 - gap * (cols - 1)) // cols
        max_h = (total_h - padding * 2 - gap * (rows - 1)) // rows
    available_w, available_h = max_w - fw, max_h - fh
    if available_w < 160 or available_h < 90:
        raise ValueError('当前屏幕空间不足，请减少窗口数、间距或留白')
    if aspect:
        units = math.floor(min(width / 16, height / 9, available_w / 16, available_h / 9))
        cw, ch = units * 16, units * 9
    else:
        cw, ch = min(width, available_w), min(height, available_h)
    outer_w, outer_h = cw + fw, ch + fh
    result = {}
    for i, key in enumerate(keys):
        dx, dy = (i * 28, i * 28) if mode == '错落排列' else ((i % cols) * (outer_w + gap), (i // cols) * (outer_h + gap))
        result[key] = (x + padding + dx, y + padding + dy, outer_w, outer_h)
    return result


def api():
    u = C.WinDLL('user32', use_last_error=True)
    u.IsWindowVisible.argtypes = [W.HWND]
    u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    u.GetWindowTextLengthW.argtypes = [W.HWND]
    u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
    u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    u.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    u.SetWindowTextW.argtypes = [W.HWND, W.LPCWSTR]
    u.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    return u


def profile_rectangles(keys, work, profiles, frame=(0, 0), **settings):
    """One shared calculation for preview and apply; heterogeneous rows never overlap."""
    if not keys:
        return {}
    x, y, w, h = map(int, work)
    columns, gap, padding = (int(settings.get(k, v)) for k, v in [('columns', 3), ('gap', 8), ('padding', 8)])
    if columns < 1 or min(gap, padding) < 0:
        raise ValueError('列数至少为 1，间距和留白不能为负')
    cols = min(columns, len(keys))
    rows = math.ceil(len(keys)/cols)
    mode = settings.get('mode', '网格排列')
    offset = max(24, gap*2)
    custom = mode == '自定义坐标'
    if custom:
        mw, mh = w, h
    elif mode == '错落排列':
        mw, mh = w-padding*2-offset*(len(keys)-1), h-padding*2-offset*(len(keys)-1)
    else:
        mw, mh = (w-padding*2-gap*(cols-1))//cols, (h-padding*2-gap*(rows-1))//rows
    fw, fh = frame
    sizes = []
    for key in keys:
        item = profiles.get(key, {})
        cw, ch = int(item.get('width', settings.get('width', 640))), int(item.get('height', settings.get('height', 360)))
        if cw < 160 or ch < 90 or mw-fw < 160 or mh-fh < 90:
            raise ValueError('窗口最小画面为 160 × 90；请调整尺寸、列数或窗口数量')
        if settings.get('aspect', True):
            units = math.floor(min(cw/16, ch/9, (mw-fw)/16, (mh-fh)/9))
            cw, ch = units*16, units*9
        else:
            cw, ch = min(cw, mw-fw), min(ch, mh-fh)
        sizes.append((cw+fw, ch+fh))
    col_width = [max([sizes[i][0] for i in range(c, len(keys), cols)]) for c in range(cols)]
    row_height = [max(v[1] for v in sizes[r*cols:(r+1)*cols]) for r in range(rows)]
    result = {}
    for i, key in enumerate(keys):
        item = profiles.get(key, {})
        dx = padding+sum(col_width[:i % cols])+gap*(i % cols)
        dy = padding+sum(row_height[:i//cols])+gap*(i//cols)
        if mode == '错落排列':
            dx = dy = padding+i*offset
        px, py = x+dx, y+dy
        if custom:
            px, py = int(item.get('x', px)), int(item.get('y', py))
        ow, oh = sizes[i]
        if px < x or py < y or px+ow > x+w or py+oh > y+h:
            raise ValueError(f'第 {i+1} 个窗口超出目标屏幕，请修改坐标或尺寸')
        result[key] = (px, py, ow, oh)
    return result


def screens():
    class Info(C.Structure):
        _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT),
                    ('flags', W.DWORD), ('device', W.WCHAR * 32)]
    u = api()
    u.GetMonitorInfoW.argtypes = [W.HMONITOR, C.POINTER(Info)]
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HMONITOR, W.HDC, C.POINTER(W.RECT), W.LPARAM)
    result = []
    @callback_type
    def callback(monitor, dc, rect, data):
        info = Info()
        info.size = C.sizeof(info)
        if u.GetMonitorInfoW(monitor, C.byref(info)):
            w = info.work
            result.append({'id': info.device, 'work': (w.left, w.top, w.right-w.left, w.bottom-w.top),
                           'primary': bool(info.flags & 1)})
        return True
    u.EnumDisplayMonitors(None, None, callback, 0)
    return sorted(result, key=lambda s: not s['primary'])


def window_for(pid):
    u = api()
    result = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def callback(hwnd, data):
        owner = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0:
            rect = W.RECT()
            u.GetWindowRect(hwnd, C.byref(rect))
            result.append(((rect.right-rect.left)*(rect.bottom-rect.top), hwnd))
        return True
    u.EnumWindows(callback, 0)
    return max(result)[1] if result else None


def guarded_window(state, stamp_fn):
    if not state.get('pid') or not state.get('stamp') or stamp_fn(state['pid']) != state['stamp']:
        raise ValueError('此角色没有仍在运行的已跟踪进程')
    hwnd = window_for(state['pid'])
    if not hwnd:
        raise ValueError('游戏窗口尚未出现')
    return hwnd


def act(state, stamp_fn, *, rectangle=None, title=None, close=False, focus=False):
    hwnd = guarded_window(state, stamp_fn)
    u = api()
    owner = W.DWORD()
    u.GetWindowThreadProcessId(hwnd, C.byref(owner))
    if owner.value != state['pid'] or stamp_fn(state['pid']) != state['stamp']:
        raise ValueError('窗口身份已变化，本次操作停止')
    if focus:
        u.IsIconic.argtypes = [W.HWND]
        u.IsIconic.restype = W.BOOL
        u.ShowWindow.argtypes = [W.HWND, C.c_int]
        u.SetForegroundWindow.argtypes = [W.HWND]
        u.SetForegroundWindow.restype = W.BOOL
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)
        if not u.SetForegroundWindow(hwnd):
            raise ValueError('窗口已找到，但系统暂不允许置前，请点击游戏任务栏图标')
    if title is not None and not u.SetWindowTextW(hwnd, title):
        raise C.WinError(C.get_last_error())
    if rectangle is not None and not u.SetWindowPos(hwnd, None, *map(int, rectangle), 0x14):
        raise C.WinError(C.get_last_error())
    if close and not u.PostMessageW(hwnd, 0x10, 0, 0):
        raise C.WinError(C.get_last_error())
    rect = W.RECT()
    u.GetWindowRect(hwnd, C.byref(rect))
    return (rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top)


def border(state, stamp_fn):
    hwnd = guarded_window(state, stamp_fn)
    outer, client = W.RECT(), W.RECT()
    u = api()
    u.GetWindowRect(hwnd, C.byref(outer))
    u.GetClientRect(hwnd, C.byref(client))
    return (outer.right-outer.left-client.right, outer.bottom-outer.top-client.bottom)



def terminate_tracked(state):
    """Verify creation time on the very handle being terminated, preventing PID reuse."""
    pid, stamp = state.get('pid'), state.get('stamp')
    if not isinstance(pid, int) or pid <= 0 or not isinstance(stamp, int) or stamp <= 0:
        raise ValueError('没有可验证的已跟踪游戏进程')
    k = C.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    k.GetProcessTimes.restype = W.BOOL
    k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    k.WaitForSingleObject.restype = W.DWORD
    k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    k.TerminateProcess.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    handle = k.OpenProcess(0x100000 | 0x1000 | 0x0001, False, pid)
    if not handle:
        if C.get_last_error() == 87:
            return False
        raise C.WinError(C.get_last_error())
    try:
        if k.WaitForSingleObject(handle, 0) == 0:
            return False
        times = [W.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(C.byref(t) for t in times)):
            raise C.WinError(C.get_last_error())
        actual = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        if actual != stamp:
            raise ValueError('进程身份已变化，已拒绝强制关闭')
        if not k.TerminateProcess(handle, 1):
            raise C.WinError(C.get_last_error())
        if k.WaitForSingleObject(handle, 5000) != 0:
            raise OSError('游戏进程尚未退出，请稍后重试')
        return True
    finally:
        k.CloseHandle(handle)
