"""Controlled single-game TCP pilot. Normal launcher routing remains disabled.

The unprivileged controller creates exactly one selected game suspended. An
elevated broker registers its PID and creation time before it can run. The private job includes ordinary descendants; this is not a claim of complete DNS or leak protection.
"""
import base64
import ctypes as C
from ctypes import wintypes as W
import importlib.machinery
import importlib.util
import json
import ipaddress
from multiprocessing.connection import Client, Listener
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid
import argparse
import hashlib

STATUS_FILE = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import proxy_support
import game_preferences
from trial_job import OwnedJob
from dns_bridge import DnsBridge


def write(file, data):
    tmp = file.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(file)
    if STATUS_FILE and file.name == "controller.json":
        write(STATUS_FILE, data)


def kernel():
    k = C.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = W.HANDLE
    k.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    k.GetProcessTimes.restype = W.BOOL
    k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    k.WaitForSingleObject.restype = W.DWORD
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.CloseHandle.argtypes = [W.HANDLE]
    k.ResumeThread.argtypes = [W.HANDLE]
    k.ResumeThread.restype = W.DWORD
    k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    k.TerminateProcess.restype = W.BOOL
    return k


def stamp(k, handle):
    times = [W.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(handle, *(C.byref(t) for t in times)):
        raise RuntimeError('Cannot verify process creation time')
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def alive(k, handle):
    return k.WaitForSingleObject(handle, 0) == 258


def ensure_owned_exit(k, handle, report, persist):
    if alive(k, handle):
        report['owned_test_game_stop_requested'] = bool(k.TerminateProcess(handle, 1))
        k.WaitForSingleObject(handle, 5000)
    while alive(k, handle):
        # Never release capture merely because termination took too long.
        report['phase'] = 'waiting_owned_game_exit_before_release'
        persist()
        time.sleep(.5)
    report['owned_game_exit_confirmed'] = True


def load_core():
    dll = C.CDLL(str(HERE / 'bin/YysProxyCore.dll'))
    dll.ProxyBridge_AddProxyConfig.argtypes = [C.c_int, C.c_char_p, W.USHORT, C.c_char_p, C.c_char_p, W.BOOL]
    dll.ProxyBridge_AddProxyConfig.restype = W.UINT
    dll.Yys_SetPidRoute.argtypes = [W.DWORD, C.c_uint64, W.UINT]
    dll.Yys_SetPidRoute.restype = W.BOOL
    dll.Yys_SetJobRoute.argtypes = [W.HANDLE, W.DWORD, W.UINT]
    dll.Yys_SetJobRoute.restype = W.BOOL
    dll.Yys_ClearJobRoute.argtypes = []
    dll.Yys_IsJobMember.argtypes = [W.DWORD]
    dll.Yys_IsJobMember.restype = W.BOOL
    dll.Yys_RemovePidRoute.argtypes = [W.DWORD]
    dll.Yys_RemovePidRoute.restype = W.BOOL
    dll.Yys_PinCapture.argtypes = [W.DWORD, C.c_uint64, C.POINTER(C.c_uint64)]
    dll.Yys_PinCapture.restype = W.BOOL
    dll.ProxyBridge_Start.restype = W.BOOL
    dll.ProxyBridge_Stop.restype = W.BOOL
    callback = C.CFUNCTYPE(None, C.c_char_p, W.DWORD, C.c_char_p, W.USHORT, C.c_char_p)
    dll.ProxyBridge_SetConnectionCallback.argtypes = [callback]
    return dll, callback


def broker(session):
    control = json.loads((session / 'control.json').read_text(encoding='utf-8'))
    report = {'phase': 'broker_starting', 'driver_active': False, 'main_pid': None,
              'system_proxy_modified': False, 'firewall_modified': False,
              'tcp_proxied': 0, 'direct_observed': 0, 'direct_loopback': 0, 'direct_external': 0, 'direct_unclassified': 0, 'blocked': 0,
              'proxied_ports': [], 'complete_game_routing_verified': False,
              'crash_fail_closed_verified': False}
    report_file = session / 'broker.json'
    write(report_file, report)
    if not C.windll.shell32.IsUserAnAdmin():
        report.update(phase='administrator_required')
        write(report_file, report)
        return
    auth = proxy_support.protect(base64.b64decode(control['auth']), True)
    listener = Listener(control['pipe'], family='AF_PIPE', authkey=auth)
    game = None
    dns_bridge = None
    job = None
    dll = None
    started = False
    k = kernel()
    callback_ref = None
    try:
        report['phase'] = 'broker_ready'
        write(report_file, report)
        with listener.accept() as conn:
            command = conn.recv()
            if command.get('op') != 'attach':
                raise RuntimeError('Unexpected command')
            pid, expected = int(command['pid']), int(command['stamp'])
            game = k.OpenProcess(0x100000 | 0x1000 | 0x0001, False, pid)
            if not game or not alive(k, game) or stamp(k, game) != expected:
                raise RuntimeError('Test process identity changed')
            query = k.QueryFullProcessImageNameW
            query.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
            query.restype = W.BOOL
            path_buf, length = C.create_unicode_buffer(32768), W.DWORD(32768)
            if not query(game, 0, path_buf, C.byref(length)):
                raise RuntimeError('Cannot verify test executable')
            if Path(path_buf.value).resolve() != Path(control['executable']).resolve():
                raise RuntimeError('Executable does not match selected test game')
            job = OwnedJob(control['job_name'])
            if not job.contains(game):
                raise RuntimeError('Game is not in the owned process family')
            spec = proxy_support.ProxyStore(ROOT).spec(control['proxy_id'])
            dll, callback_type = load_core()
            @callback_type
            def observe(name, owner, dest, port, info):
                if owner != pid and not dll.Yys_IsJobMember(owner):
                    return
                text = (info or b'').lower()
                if b'proxy' in text:
                    report['tcp_proxied'] += 1
                    if port not in report['proxied_ports']:
                        report['proxied_ports'].append(port)
                elif text.startswith(b'direct'):
                    report['direct_observed'] += 1
                    try:
                        local = ipaddress.ip_address(dest.decode('ascii')).is_loopback
                        report['direct_loopback' if local else 'direct_external'] += 1
                    except (ValueError, UnicodeError):
                        report['direct_unclassified'] += 1
                elif text.startswith(b'blocked'):
                    report['blocked'] += 1
            callback_ref = observe
            dll.ProxyBridge_SetConnectionCallback(callback_ref)
            config = dll.ProxyBridge_AddProxyConfig(1, spec['host'].encode(), spec['port'],
                                                    spec['username'].encode(), spec['password'].encode(), False)
            if not config or not dll.Yys_SetPidRoute(pid, expected, config):
                raise RuntimeError('Cannot register test route')
            if not dll.Yys_SetJobRoute(job.handle, pid, config):
                raise RuntimeError('Cannot protect owned process family')
            report['process_family_routing'] = True
            # Kept off until process-owned packet capture passes on this host.
            report['dns_capture_enabled'] = False
            if control.get('enable_process_dns') is True:
                dns_bridge = DnsBridge(dll, spec, report)
                report['dns_capture_enabled'] = True
            report.update(phase='starting_engine', main_pid=pid)
            write(report_file, report)
            if not dll.ProxyBridge_Start():
                raise RuntimeError('Engine startup failed')
            started = True
            pinned = C.c_uint64()
            if not dll.Yys_PinCapture(int(command['guard_pid']), int(command['guard_stamp']), C.byref(pinned)):
                raise RuntimeError('Independent capture guard was not established')
            report['capture_pinned'] = True
            report.update(phase='routing', driver_active=True)
            write(report_file, report)
            conn.send({'ready': True, 'capture_pin': pinned.value})
            last = time.monotonic()
            while alive(k, game):
                if conn.poll(.5):
                    command = conn.recv()
                    last = time.monotonic()
                    if command.get('op') == 'status':
                        report['family_processes'] = job.count()
                        write(report_file, report)
                        conn.send(dict(report))
                    else:
                        raise RuntimeError('Unexpected controller command')
                if time.monotonic() - last > 6:
                    raise RuntimeError('Controller heartbeat lost')
            report['phase'] = 'game_exited'
    except (EOFError, BrokenPipeError) as error:
        if game and not alive(k, game):
            report['phase'] = 'game_exited'
        else:
            report.update(phase='controller_disconnected', error_type=type(error).__name__)
    except Exception as error:
        report.update(phase='failed', error_type=type(error).__name__)
    finally:
        # The capture outlives every owned descendant, including cleanup faults.
        if job:
            job.stop_and_wait(report, lambda: write(report_file, report))
        if game:
            ensure_owned_exit(k, game, report, lambda: write(report_file, report))
        if dns_bridge:
            dns_bridge.close()
        if dll:
            dll.Yys_ClearJobRoute()
        if dll and report.get('main_pid'):
            dll.Yys_RemovePidRoute(report['main_pid'])
        if started:
            report['engine_stopped'] = bool(dll.ProxyBridge_Stop())
        report['driver_active'] = False
        if game:
            k.CloseHandle(game)
        if job:
            job.close()
        listener.close()
        write(report_file, report)


def check_cancelled():
    if STATUS_FILE and STATUS_FILE.with_suffix('.cancel').exists():
        raise RuntimeError('Startup cancelled')


def error_message(error):
    return {
        'Startup cancelled': '代理启动已取消，未回退直连',
        'Administrator authorization cancelled': '已取消管理员授权；代理角色未启动',
        'Broker did not become ready': '等待代理组件超时；请检查管理员授权后重试',
        'Broker heartbeat lost': '代理组件失去响应，已请求关闭所选角色',
        'Another TCP trial is active': '已有代理角色运行，请先关闭该角色',
        'Cannot resume verified test game': '游戏恢复运行失败，请重试',
    }.get(str(error), '代理启动异常，请检查代理及管理员授权后重试；未回退直连')


def controller(role_id, selected_proxy=None, preferences=None):
    import _winapi
    loader = importlib.machinery.SourceFileLoader('trial_business', str(ROOT / 'launcher.pyw'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    app = importlib.util.module_from_spec(spec)
    loader.exec_module(app)
    cfg = app.read_json(ROOT / 'data/accounts.json', {})
    role = next(a for a in cfg['accounts'] if a['id'] == role_id)
    if not role.get('confirmed'):
        raise RuntimeError('Use a confirmed saved test role')
    profile = app.account_folder(ROOT / 'data/profiles', role_id)
    previous = app.read_json(profile / 'running.json', {})
    if previous.get('pid') and app.process_stamp(previous['pid']) == previous.get('stamp'):
        raise RuntimeError('Selected role is already running')
    proxies = [p for p in proxy_support.ProxyStore(ROOT).public() if p.get('enabled')]
    chosen = next((p for p in proxies if p['id'] == (selected_proxy or role.get('proxy_id'))), None)
    if not chosen and not selected_proxy and len(proxies) == 1:
        chosen = proxies[0]
    if not chosen:
        raise RuntimeError('Select exactly one test proxy')
    game, executable = app.find_game(cfg['game'])
    profile, cwd, env = app.prepare(ROOT / 'data/profiles', game, role_id) if preferences is None else app.prepare(ROOT / 'data/profiles', game, role_id, game_preferences.normalize(preferences))
    session = HERE / 'sessions' / uuid.uuid4().hex
    session.mkdir(parents=True)
    auth = secrets.token_bytes(32)
    endpoint = r'\\.\pipe\YysProxyTrial-' + session.name
    control = {'role_id': role_id, 'proxy_id': chosen['id'], 'pipe': endpoint,
               'executable': str(cwd / executable.relative_to(game)),
               'job_name': 'Local\\YysProxyFamily-' + session.name,
               'auth': base64.b64encode(proxy_support.protect(auth)).decode()}
    write(session / 'control.json', control)
    report = {'phase': 'creating_suspended_game', 'role': role.get('nickname') or role.get('name'),
              'server': role.get('server'), 'main_pid': None,
              'tcp_only_experiment': True, 'crash_fail_closed_verified': False}
    write(session / 'controller.json', report)
    write(HERE / 'latest-game-trial.json', {'session': str(session)})
    hp = ht = None
    job = None
    pinned_capture = None
    conn = None
    k = kernel()
    try:
        check_cancelled()
        job = OwnedJob(control['job_name'], create=True)
        hp, ht, pid, _ = _winapi.CreateProcess(control['executable'],
            subprocess.list2cmdline([control['executable']]), None, None, False,
            0x00000004 | 0x00000400, env, str(cwd), subprocess.STARTUPINFO())
        job.assign(W.HANDLE(hp))
        report['process_family_assigned'] = True
        created = stamp(k, W.HANDLE(hp))
        app.write_json(profile / 'running.json', {'pid': pid, 'stamp': created, 'proxy_trial': session.name})
        report.update(phase='waiting_administrator', main_pid=pid)
        write(session / 'controller.json', report)
        # Only session path is passed on the command line; no proxy credentials.
        args = subprocess.list2cmdline([str(Path(__file__).resolve()), '--broker', str(session)])
        shell = C.windll.shell32.ShellExecuteW
        shell.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, C.c_int]
        shell.restype = C.c_void_p
        rc = shell(None, 'runas', sys.executable, args, str(HERE), 0)
        if not rc or rc <= 32:
            raise RuntimeError('Administrator authorization cancelled')
        check_cancelled()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            check_cancelled()
            broker_file = session / 'broker.json'
            if broker_file.exists():
                state = json.loads(broker_file.read_text(encoding='utf-8'))
                if state['phase'] == 'broker_ready':
                    break
                if state['phase'] in ('failed', 'administrator_required'):
                    raise RuntimeError('Broker initialization failed')
            time.sleep(.2)
        else:
            raise RuntimeError('Broker did not become ready')
        conn = Client(endpoint, family='AF_PIPE', authkey=auth)
        conn.send({'op': 'attach', 'pid': pid, 'stamp': created,
                   'guard_pid': __import__('os').getpid(), 'guard_stamp': stamp(k, k.GetCurrentProcess())})
        if not conn.poll(20):
            raise RuntimeError('Routing was not ready; suspended game will be stopped')
        ready = conn.recv()
        if not ready.get('ready') or not ready.get('capture_pin'):
            raise RuntimeError('Capture protection missing; suspended game will be stopped')
        pinned_capture = W.HANDLE(int(ready['capture_pin']))
        check_cancelled()
        report['capture_pinned'] = True
        app.write_json(profile / 'running.json', {'pid': pid, 'stamp': created, 'proxy_trial': session.name})
        if k.ResumeThread(W.HANDLE(ht)) == 0xFFFFFFFF:
            raise RuntimeError('Cannot resume verified test game')
        _winapi.CloseHandle(ht)
        ht = None
        report['phase'] = 'running_tcp_trial'
        write(session / 'controller.json', report)
        # Normal-integrity controller checks the elevated broker continuously.
        while alive(k, W.HANDLE(hp)):
            check_cancelled()
            conn.send({'op': 'status'})
            if not conn.poll(1):
                raise RuntimeError('Broker heartbeat lost')
            status = conn.recv()
            report.update(dns_queries=status.get('dns_queries',0), dns_proxied=status.get('dns_proxied',0), dns_failed=status.get('dns_failed',0), dns_capture_enabled=status.get('dns_capture_enabled',False), dns_process_owned_only=True, family_processes=status.get('family_processes', 1), process_family_routing=status.get('process_family_routing', False), tcp_proxied=status['tcp_proxied'], direct_observed=status['direct_observed'],
                          proxied_ports=status['proxied_ports'], blocked=status['blocked'], direct_loopback=status.get('direct_loopback',0), direct_external=status.get('direct_external',0), direct_unclassified=status.get('direct_unclassified',0))
            write(session / 'controller.json', report)
            time.sleep(.5)
        report['phase'] = 'game_exited'
    except (EOFError, BrokenPipeError) as error:
        if hp and not alive(k, W.HANDLE(hp)):
            report['phase'] = 'game_exited'
        else:
            report.update(phase='broker_disconnected', error_type=type(error).__name__)
    except Exception as error:
        report.update(phase='failed', error_type=type(error).__name__, message=error_message(error))
    finally:
        if job:
            job.stop_and_wait(report, lambda: write(session / 'controller.json', report))
        if hp:
            ensure_owned_exit(k, W.HANDLE(hp), report, lambda: write(session / 'controller.json', report))
        if conn:
            conn.close()
        # The independent capture must outlive the owned game, including faults.
        if pinned_capture:
            k.CloseHandle(pinned_capture)
            report['capture_pin_released_after_game_exit'] = True
        if ht:
            _winapi.CloseHandle(ht)
        if hp:
            _winapi.CloseHandle(hp)
        if job:
            job.close()
        write(session / 'controller.json', report)


def main():
    global STATUS_FILE
    parser = argparse.ArgumentParser()
    parser.add_argument('--broker')
    parser.add_argument('--role')
    parser.add_argument('--proxy')
    parser.add_argument('--ticket')
    parser.add_argument('--game-prefs')
    args = parser.parse_args()
    if args.broker:
        broker(Path(args.broker).resolve())
        return
    if not args.role or not args.proxy:
        parser.error('An explicit role and proxy are required')
    if args.ticket:
        if uuid.UUID(args.ticket).hex != args.ticket:
            raise ValueError('Invalid ticket')
        STATUS_FILE = HERE / 'tickets' / (args.ticket + '.json')
        STATUS_FILE.parent.mkdir(exist_ok=True)
    k = kernel()
    k.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
    k.CreateMutexW.restype = W.HANDLE
    name = 'Local\\YysProxyTrial-' + hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:24]
    lock = k.CreateMutexW(None, False, name)
    already = C.get_last_error() == 183
    try:
        if not lock or already:
            raise RuntimeError('Another TCP trial is active')
        controller(args.role, args.proxy, json.loads(args.game_prefs) if args.game_prefs else None)
    except Exception as error:
        if STATUS_FILE:
            write(STATUS_FILE, {'phase': 'failed', 'error_type': type(error).__name__,
                               'message': error_message(error)})
        else:
            raise
    finally:
        if lock:
            k.CloseHandle(lock)


if __name__ == '__main__':
    main()
