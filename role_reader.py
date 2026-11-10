"""Read role identity from this game window's own configuration; no injection or external helper."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path

GAME_NAMES = {'onmyoji.exe', 'onmyoji_future.exe', 'client.exe', 'aclient.exe'}


def game_pids():
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        func = getattr(kernel, name)
        func.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        func.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            if entry.szExeFile.lower() in GAME_NAMES:
                result.add(int(entry.th32ProcessID))
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
        return result
    finally:
        kernel.CloseHandle(handle)


def parse_identity(payload, servers):
    if isinstance(payload, dict) and payload.get('error'):
        raise ValueError('尚未读到已登录角色，请进入庭院后重试')
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list) or len(payload[0]) < 4:
        raise ValueError('尚未读到角色信息，请先登录并进入庭院')
    short_id, server_id, nickname, level = payload[0][:4]
    if not isinstance(nickname, str) or not nickname.strip() or not isinstance(level, int) or level <= 0:
        raise ValueError('尚未读到已登录角色，请进入庭院后重试')
    if isinstance(short_id, bool) or not str(short_id).isdigit() or int(short_id) <= 0:
        raise ValueError('角色标识无效，请完成登录后重新读取')
    server_id = str(server_id)
    if not server_id.isdigit() or int(server_id) <= 0:
        raise ValueError('区服编号无效，请完成登录后重新读取')
    catalog = {str(item['id']): item for item in servers}
    entry = catalog.get(server_id, {})
    return {'short_id': str(short_id), 'server_id': server_id,
            'nickname': nickname.strip(), 'server': entry.get('name') or f'区服 {server_id}',
            'server_known': bool(entry.get('name'))}


def read_client_config(file):
    raw = Path(file).read_text(encoding='utf-8')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(bytes.fromhex(raw))
    if not isinstance(data, dict):
        raise ValueError('游戏配置格式无效')
    return data


def historical_roles(config):
    records = config.get('local_all_login_record', {})
    if not isinstance(records, dict):
        raise ValueError('游戏角色历史记录格式无效')
    result = []
    for zones in records.values():
        if not isinstance(zones, dict):
            continue
        for entries in zones.values():
            if not isinstance(entries, list):
                continue
            for row in entries:
                if not isinstance(row, dict):
                    continue
                if (row.get('player_name') and str(row.get('player_id', '')).isdigit()
                        and str(row.get('server_id', '')).isdigit()):
                    result.append(row)
    return result


def identity_from_record(row, servers):
    identity = parse_identity([[row.get('player_id'), row.get('server_id'),
                                row.get('player_name'), row.get('player_level', 1)]], servers)
    if row.get('server_name'):
        identity['server'] = str(row['server_name'])
        identity['server_known'] = True
    return identity


def select_current_identity(config, servers, launched_at):
    server_id = str(config.get('areaSetId', ''))
    candidates = []
    for row in historical_roles(config):
        try:
            timestamp = float(row.get('login_time', 0))
        except (TypeError, ValueError):
            continue
        if timestamp > 1e12:
            timestamp /= 1000
        if str(row.get('server_id')) == server_id and timestamp >= launched_at - 2:
            candidates.append((timestamp, row))
    if not candidates:
        raise ValueError('尚未发现本次登录记录，请进入庭院后等待配置保存；不会使用旧登录记录绑定角色')
    latest = max(t for t, row in candidates)
    newest = [row for t, row in candidates if t == latest]
    unique = {(str(row.get('player_id')), str(row.get('server_id'))) for row in newest}
    if len(unique) != 1:
        raise ValueError('本次登录角色记录不唯一，请重新登录目标角色后再读取')
    return identity_from_record(newest[0], servers)


def read_identity(expected_pid, expected_stamp, stamp_fn, config_file, servers):
    if stamp_fn(expected_pid) != expected_stamp:
        raise ValueError('原游戏窗口已退出，请重新启动该角色')
    # Windows process creation time is measured in 100 ns ticks since 1601.
    launched_at = expected_stamp / 10000000 - 11644473600
    try:
        config = read_client_config(config_file)
    except FileNotFoundError:
        raise ValueError('游戏尚未生成角色配置，请先完成登录并进入庭院') from None
    except (ValueError, UnicodeError):
        raise ValueError('游戏配置正在保存，请稍后重试') from None
    identity = select_current_identity(config, servers, launched_at)
    if stamp_fn(expected_pid) != expected_stamp:
        raise ValueError('游戏窗口已变化，本次结果不保存')
    return identity


def confirm_role(config, account_id, identity):
    # Called only after the user's confirmation dialog returned Yes.
    duplicate = next((a for a in config['accounts'] if a['id'] != account_id
                      and a.get('short_id') == identity['short_id']
                      and a.get('server_id') == identity['server_id']), None)
    if duplicate:
        raise ValueError('这个角色已经保存，请使用列表中的原角色')
    role = next((a for a in config['accounts'] if a['id'] == account_id), None)
    if role is None:
        role = next((a for a in config.get('pending', []) if a['id'] == account_id), None)
    if role is None:
        raise ValueError('未找到待绑定窗口')
    if role.get('target_short_id') and (role['target_short_id'] != identity['short_id'] or role.get('target_server_id') != identity['server_id']):
        raise ValueError('登录角色与所选导入角色不一致，请切换到目标角色后重新读取')
    role = {**role, **identity, 'name': identity['nickname'], 'confirmed': True}
    updated = dict(config)
    updated['accounts'] = [a for a in config['accounts'] if a['id'] != account_id] + [role]
    updated['pending'] = [a for a in config.get('pending', []) if a['id'] != account_id]
    return updated
