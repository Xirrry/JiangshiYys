"""Independent Windows launcher. Python 3.12+, standard library only."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CONFIG = DATA / 'accounts.json'
SHARED = ('bin', 'bin_patch', 'res', 'zipres', 'thd', 'thdext1')
DOCUMENT_RESOURCES = ('cloudfilesys3', 'res', 'script', 'SubRes', 'movie',
                      'sound', 'map', 'ui', 'voice', 'videodownload', 'thd', 'thdext1', 'zipres')
VERSION_KEYS = ('last_app_version', 'last_patch_version', 'last_script_version',
                'last_res_version', 'last_engine_version')


def resource_link(source, dest, profile):
    import _winapi
    if not source.is_dir():
        return
    if os.path.lexists(dest):
        if dest.is_junction() or dest.is_symlink():
            if dest.resolve() != source.resolve():
                raise ValueError(f'资源链接指向其他位置，不会覆盖：{dest}')
            return
        # Rename exactly one private directory, retaining partial downloads.
        # Both paths must stay inside this account, never inside shared game data.
        if not dest.is_dir() or not dest.resolve().is_relative_to(profile.resolve()):
            raise ValueError(f'资源目录不可安全迁移：{dest}')
        backup = dest.with_name(dest.name + '.before-resource-fix-' + str(time.time_ns()))
        if not backup.parent.resolve().is_relative_to(profile.resolve()):
            raise ValueError('备份路径超出账号目录')
        dest.rename(backup)
        try:
            _winapi.CreateJunction(str(source), str(dest))
        except OSError:
            backup.rename(dest)
            raise
    else:
        _winapi.CreateJunction(str(source), str(dest))


def game_config(file):
    if not file.exists():
        return {}, True
    raw = file.read_text(encoding='utf-8')
    try:
        value = json.loads(raw)
        hexadecimal = False
    except json.JSONDecodeError:
        value = json.loads(bytes.fromhex(raw))
        hexadecimal = True
    if not isinstance(value, dict):
        raise ValueError(f'游戏配置不是对象：{file}')
    return value, hexadecimal


def sync_resource_versions(game, cwd):
    # These files use hex-encoded JSON on the tested client. Never copy account,
    # login records, device identity, or server choice from the original client.
    for name in ('clientconfig', 'cloudconfig'):
        source = game / 'Documents' / name
        if not source.is_file():
            continue
        original, _ = game_config(source)
        dest = cwd / 'Documents' / name
        if dest.is_symlink() or dest.is_junction():
            raise ValueError(f'账号配置不能是链接：{dest}')
        current, hexadecimal = game_config(dest)
        keys = VERSION_KEYS if name == 'clientconfig' else tuple(k for k in original if k.startswith('done_'))
        updates = {key: original[key] for key in keys if key in original}
        if not updates or all(current.get(k) == v for k, v in updates.items()):
            continue
        if dest.exists():
            shutil.copy2(dest, dest.with_name(dest.name + '.before-resource-fix-' + str(time.time_ns())))
        current.update(updates)
        raw = json.dumps(current, ensure_ascii=False, separators=(',', ':'))
        temp = dest.with_name(dest.name + '.resource-fix.tmp')
        temp.write_text(raw.encode('utf-8').hex() if hexadecimal else raw, encoding='utf-8')
        os.replace(temp, dest)


def read_json(file, default):
    if not file.exists():
        return default
    return json.loads(file.read_text(encoding='utf-8'))


def write_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, file)


def private_dir(folder):
    if folder.is_symlink() or folder.is_junction():
        raise ValueError(f'独立目录不能是链接：{folder}')
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def process_stamp(pid):
    """Creation time guards against Windows reusing a PID. Deny uncertain access."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise OSError('无法确认账号进程是否仍在运行；请退出游戏后重试')
    try:
        if kernel.WaitForSingleObject(handle, 0) == 0:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def account_folder(base, account_id):
    key = hashlib.sha256(account_id.encode('utf-8')).hexdigest()[:24]
    return base / key


def prepare(base, game, account_id, preferences=None):
    import _winapi
    private_dir(base)
    profile = private_dir(account_folder(base, account_id))
    state = read_json(profile / 'running.json', {})
    if state.get('pid') and process_stamp(state['pid']) == state.get('stamp'):
        raise ValueError('此账号仍在运行，请正常退出游戏后再修复资源目录')
    for rel in ('AppData', 'AppData/Roaming', 'AppData/Roaming/Netease',
                'AppData/Roaming/Netease/Mpay', 'AppData/Local', 'AppData/Local/Temp',
                'Documents', 'Pictures', 'Downloads', 'game', 'game/Documents',
                'game/cefLocalStorage', 'game/crashdumps', 'game/.paz'):
        private_dir(profile / rel)
    cwd = profile / 'game'
    for name in SHARED:
        source, dest = game / name, cwd / name
        if not source.is_dir():
            continue
        if os.path.lexists(dest):
            if not dest.is_junction() or dest.resolve() != source.resolve():
                raise ValueError(f'资源路径已被占用，不会覆盖：{dest}')
        else:
            _winapi.CreateJunction(str(source), str(dest))
    for name in DOCUMENT_RESOURCES:
        resource_link(game / 'Documents' / name, cwd / 'Documents' / name, profile)
    sync_resource_versions(game, cwd)
    for source in game.iterdir():
        if source.is_symlink() or not source.is_file():
            continue
        if source.suffix.lower() not in ('.exe', '.dll', '.ini', '.xml', '.json', '.ico') and source.name not in ('win_version', 'yys-mumu-d'):
            continue
        dest = cwd / source.name
        if os.path.lexists(dest):
            if dest.is_symlink() or not dest.is_file():
                raise ValueError(f'账号配置路径无效：{dest}')
        else:
            # Exclusive creation keeps any existing account configuration intact.
            with source.open('rb') as src, dest.open('xb') as dst:
                shutil.copyfileobj(src, dst)
    overrides = {
        'USERPROFILE': str(profile), 'APPDATA': str(profile / 'AppData/Roaming'),
        'LOCALAPPDATA': str(profile / 'AppData/Local'),
        'TEMP': str(profile / 'AppData/Local/Temp'), 'TMP': str(profile / 'AppData/Local/Temp'),
        'HOMEDRIVE': profile.drive, 'HOMEPATH': str(profile)[len(profile.drive):],
    }
    env = {k: v for k, v in os.environ.items() if k.upper() not in overrides}
    env.update(overrides)
    import game_preferences
    prefs = game_preferences.resolve(read_json(CONFIG, {}), account_id) if preferences is None else game_preferences.normalize(preferences)
    game_preferences.apply(cwd / 'Documents/clientconfig', base, prefs)
    return profile, cwd, env


def find_game(value):
    game = Path(value).expanduser().resolve()
    if game.is_file():
        selected = game
        game = game.parent.parent if game.parent.name.lower() == 'bin' else game.parent
        if selected.name.lower() in ('onmyoji.exe', 'onmyoji_future.exe'):
            return game, selected
    for rel in ('bin/onmyoji.exe', 'bin/onmyoji_future.exe', 'onmyoji.exe'):
        exe = game / rel
        if exe.is_file():
            return game, exe
    raise ValueError('未找到 bin/onmyoji.exe，请选择阴阳师游戏目录')


def launch(game, executable, account_id, preferences=None):
    base = DATA / 'profiles'
    folder = account_folder(base, account_id)
    state = read_json(folder / 'running.json', {})
    if state.get('pid') and process_stamp(state['pid']) == state.get('stamp'):
        raise ValueError('此账号仍在运行，请先正常退出游戏')
    profile, cwd, env = prepare(base, game, account_id, preferences)
    child = subprocess.Popen([str(cwd / executable.relative_to(game))], cwd=cwd, env=env)
    stamp = process_stamp(child.pid)
    if stamp is None:
        raise RuntimeError('游戏启动后立即退出，请检查客户端能否正常运行')
    write_json(folder / 'running.json', {'pid': child.pid, 'stamp': stamp})
    return child, profile


def main():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    import queue
    import threading
    import role_reader
    import launcher_workspace
    try:
        ctypes.WinDLL('user32').SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass

    window = tk.Tk()
    launcher_workspace.theme(window)
    window.withdraw()
    try:
        import msvcrt
        private_dir(DATA)
        instance_lock = (DATA / 'launcher.lock').open('a+b')
        instance_lock.seek(0)
        if not instance_lock.read(1):
            instance_lock.write(b'0')
            instance_lock.flush()
        instance_lock.seek(0)
        msvcrt.locking(instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        messagebox.showerror('提示', '该目录的启动器已经打开，或目录不可写。')
        window.destroy()
        return
    try:
        config = read_json(CONFIG, {'game': 'D:/Game/yys', 'accounts': [], 'pending': []})
        config.setdefault('pending', [])
        servers = read_json(ROOT / 'servers.json', {'servers': []})['servers']
    except (ValueError, OSError, KeyError, TypeError) as error:
        messagebox.showerror('配置读取失败', str(error))
        window.destroy()
        return
    source_stamp = Path(__file__).stat().st_mtime_ns
    window.title('阴阳师角色启动器 · 自定义排列版 v8')
    window.geometry('1380x900')
    window.minsize(1180, 780)
    window.deiconify()
    body = ttk.Frame(window, padding=16)
    body.pack(fill='both', expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(4, weight=1)
    ttk.Label(body, text='阴阳师角色启动器', font=('Microsoft YaHei UI', 16, 'bold')).grid(row=0, column=0, sticky='w')
    ttk.Label(body, text='账号分组  /  平安志同步  /  多窗口排列' , style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(4, 12))
    path_frame = ttk.Frame(body)
    path_frame.grid(row=2, column=0, sticky='ew', pady=(0, 8))
    game_var = tk.StringVar(value=config.get('game', 'D:/Game/yys'))
    ttk.Label(path_frame, text='游戏目录：').pack(side='left')
    ttk.Entry(path_frame, textvariable=game_var).pack(side='left', fill='x', expand=True)
    def choose_game():
        selected = filedialog.askdirectory(title='选择阴阳师游戏目录')
        if selected:
            game_var.set(selected)
    ttk.Button(path_frame, text='浏览', command=choose_game).pack(side='left', padx=(8, 0))
    toolbar = ttk.Frame(body)
    toolbar.grid(row=3, column=0, sticky='ew', pady=(0, 10))
    content = ttk.Frame(body)
    content.grid(row=4, column=0, sticky='nsew')
    content.columnconfigure(0, weight=1)
    content.rowconfigure(0, weight=1)
    left = ttk.Frame(content, padding=(0, 0, 18, 0))
    left.grid(row=0, column=0, sticky='nsew')
    left.columnconfigure(0, weight=1)
    left.rowconfigure(2, weight=1)
    right = ttk.Frame(content, width=360)
    right.grid(row=0, column=1, sticky='nsew')
    tree = launcher_workspace.AccountTree(left, lambda: config, columns=('name', 'server', 'state'), show='tree headings', selectmode='extended')
    for key, label, width in [('name', '角色昵称', 185), ('server', '区服', 145), ('state', '状态', 225)]:
        tree.heading(key, text=label)
        tree.column(key, width=width)
    tree.grid(row=2, column=0, sticky='nsew')
    scrollbar = ttk.Scrollbar(left, orient='vertical', command=tree.yview)
    scrollbar.grid(row=2, column=1, sticky='ns')
    tree.configure(yscrollcommand=scrollbar.set)
    workspace = None
    log = tk.Text(body, height=4, wrap='word', state='disabled', bg='#fffdf8', fg='#6f6052', relief='flat', padx=12, pady=8, font=('Microsoft YaHei UI', 9))
    log.grid(row=6, column=0, sticky='ew', pady=(10, 0))
    def note(text):
        log.configure(state='normal')
        log.insert('end', f'{time.strftime("%H:%M:%S")}  {text}\n')
        log.see('end')
        log.configure(state='disabled')
    def current_version():
        if Path(__file__).stat().st_mtime_ns != source_stamp:
            messagebox.showinfo('请重启', '启动器已更新，请关闭此窗口后重新打开。')
            return False
        return True
    def save(next_config=None):
        nonlocal config
        candidate = dict(config if next_config is None else next_config)
        candidate['game'] = game_var.get().strip()
        write_json(CONFIG, candidate)
        config = candidate
    def rows():
        return config['accounts'] + config['pending']
    def find(account_id):
        return next(a for a in rows() if a['id'] == account_id)
    def refresh_row(account_id, status=None):
        a = find(account_id)
        is_pending = not a.get('confirmed')
        legacy_cache = a.get('imported') and a.get('cache_mode') != 'fresh-single-role'
        values = (a.get('nickname') or a.get('name') or '新角色（等待登录）',
                  a.get('server') or '待读取',
                  status or ('旧版混合缓存 · 需重新绑定' if legacy_cache else '待登录 / 待确认' if is_pending else '已保存'))
        if tree.exists(account_id):
            tree.item(account_id, values=values)
        else:
            tree.insert('', 'end', iid=account_id, values=values)
    for account in rows():
        refresh_row(account['id'])
    children = []
    binding = None
    next_read = 0
    busy = False
    results = queue.Queue()
    previous_error = ''
    def enable_binding(account_id):
        nonlocal binding, next_read, previous_error
        binding = account_id
        next_read = time.monotonic() + 8
        previous_error = ''
        note('请在新游戏窗口自行登录并进入庭院；启动器随后自动读取昵称、区服。')
    def launch_row(account_id):
        game, executable = find_game(game_var.get().strip())
        child, profile = launch(game, executable, account_id)
        children.append((child, account_id))
        refresh_row(account_id, f'运行中 · PID {child.pid}')
        note(f'已启动 {find(account_id).get("name", "新角色")}，PID {child.pid}')
        if workspace:
            workspace.on_launch(account_id)
        return child
    def add_role():
        if not current_version() or busy:
            return
        try:
            if binding:
                raise ValueError('已有正在识别的角色，请先完成确认或暂停识别。')
            account_id = uuid.uuid4().hex
            draft = {'id': account_id, 'name': '新角色（等待登录）', 'confirmed': False}
            next_config = {**config, 'pending': config['pending'] + [draft]}
            save(next_config)
            refresh_row(account_id)
            tree.selection_set(account_id)
            launch_row(account_id)
            enable_binding(account_id)
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror('无法添加角色', str(error))
    def start_selected():
        if not current_version() or busy:
            return
        selected = tree.launch_ids()
        if not selected:
            messagebox.showinfo('提示', '请选择已保存角色，或点击“添加角色并登录”。')
            return
        try:
            if binding:
                raise ValueError('请先完成当前角色的确认，或暂停识别后再多开。')
            if any(find(a).get('imported') and find(a).get('cache_mode') != 'fresh-single-role' for a in selected):
                if len(selected) != 1:
                    raise ValueError('旧版导入角色请先单独重新绑定，再进行多开。')
                old = find(selected[0])
                if not messagebox.askyesno('改为单角色缓存', '此角色使用旧版复制的混合缓存。\n将新建空白登录目录，只登录这个角色所属账号。\n旧目录保留，首次需要重新登录。\n\n是否继续？'):
                    return
                import cache_import
                game, executable = find_game(game_var.get().strip())
                identity = {k: old[k] for k in ('nickname', 'server', 'server_id', 'short_id', 'server_known')}
                fresh = cache_import.fresh_role(prepare, DATA / 'profiles', game, identity, servers)
                fresh['group'] = old.get('group') or '未分组'
                save({**config, 'accounts': [a for a in config['accounts'] if a['id'] != old['id']], 'pending': config['pending'] + [fresh]})
                tree.delete(old['id'])
                refresh_row(fresh['id'])
                selected = (fresh['id'],)
                tree.selection_set(fresh['id'])
            if any(not find(a).get('confirmed') for a in selected):
                if len(selected) != 1:
                    raise ValueError('一次只启动一个待识别角色，完成确认后再添加下一个。')
            save()
            for account_id in selected:
                launch_row(account_id)
            if len(selected) == 1 and not find(selected[0]).get('confirmed'):
                enable_binding(selected[0])
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror('启动提示', str(error))
    def begin_read(account_id):
        nonlocal busy
        if busy:
            return
        try:
            state = read_json(account_folder(DATA / 'profiles', account_id) / 'running.json', {})
            target_pid, stamp = state['pid'], state['stamp']
            if process_stamp(target_pid) != stamp:
                raise ValueError('该角色窗口已退出，请先启动所选角色。')
        except (OSError, ValueError, KeyError) as error:
            results.put((account_id, None, str(error)))
            return
        busy = True
        refresh_row(account_id, '正在识别昵称和区服…')
        config_file = account_folder(DATA / 'profiles', account_id) / 'game/Documents/clientconfig'
        def worker():
            try:
                identity = role_reader.read_identity(target_pid, stamp, process_stamp, config_file, servers)
                results.put((account_id, identity, None))
            except Exception as error:
                results.put((account_id, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()
    def manual_read():
        nonlocal binding, next_read, previous_error
        if not current_version() or busy:
            return
        selected = tree.selection()
        if len(selected) != 1:
            messagebox.showinfo('提示', '请选择一个已经登录的角色窗口。')
            return
        binding = selected[0]
        next_read = float('inf')
        previous_error = ''
        begin_read(binding)
    def pause():
        nonlocal binding
        if busy:
            messagebox.showinfo('提示', '正在读取，请等本次读取结束。')
            return
        binding = None
        note('已暂停自动识别；未确认的角色仍保留在“待确认”列表。')
    def sync_pinganzhi():
        import pinganzhi_sync
        if not current_version() or busy:
            return
        if binding:
            messagebox.showinfo('提示', '请先完成当前角色确认，或暂停识别后再同步。')
            return
        dialog = tk.Toplevel(window)
        dialog.title('从平安志同步账号')
        dialog.geometry('850x510')
        dialog.transient(window)
        dialog.grab_set()
        root_var = tk.StringVar(value=config.get('pinganzhi_root', str(pinganzhi_sync.default_root())))
        paths = ttk.Frame(dialog, padding=12)
        paths.pack(fill='x')
        ttk.Label(paths, text='平安志账号目录：').pack(side='left')
        ttk.Entry(paths, textvariable=root_var).pack(side='left', fill='x', expand=True)
        sources = []
        choices = ttk.Treeview(dialog, columns=('nickname', 'server', 'status'), show='headings', selectmode='extended')
        for key, label, width in [('nickname', '昵称', 250), ('server', '区服', 230), ('status', '状态', 250)]:
            choices.heading(key, text=label)
            choices.column(key, width=width)
        choices.pack(fill='both', expand=True, padx=12)
        def refresh_sources():
            nonlocal sources
            try:
                sources = pinganzhi_sync.scan_accounts(Path(root_var.get().strip()))
                for item in choices.get_children():
                    choices.delete(item)
                for i, source in enumerate(sources):
                    existed = any(a.get('pinganzhi_source_id') == source['meta']['id'] for a in rows())
                    choices.insert('', 'end', iid=str(i), values=(source['nickname'], source['server'], '已同步，可更新' if existed else '可同步'))
                if not sources:
                    messagebox.showinfo('未发现账号', '未发现已保存且有登录缓存的平安志账号。', parent=dialog)
            except (OSError, ValueError) as error:
                messagebox.showerror('读取失败', str(error), parent=dialog)
        def choose_root():
            selected = filedialog.askdirectory(title='选择平安志 desktop-accounts 目录', parent=dialog)
            if selected:
                root_var.set(selected)
                refresh_sources()
        ttk.Button(paths, text='选择目录', command=choose_root).pack(side='left', padx=8)
        ttk.Button(paths, text='刷新', command=refresh_sources).pack(side='left')
        ttk.Label(dialog, text='仅复制选中的平安志账号目录中的登录缓存和配置，不扫描原游戏账号。\n请先退出对应游戏窗口；同名角色更新为新副本，旧目录保留。按 Ctrl 可多选。', padding=12).pack(anchor='w')
        def accept_sync():
            selected = choices.selection()
            if not selected:
                return
            succeeded = 0
            for item in selected:
                source = sources[int(item)]
                try:
                    if not current_version():
                        return
                    game, executable = find_game(game_var.get().strip())
                    duplicate = next((a for a in rows() if a.get('pinganzhi_source_id') == source['meta']['id']
                                      or (a.get('nickname') == source['nickname'] and a.get('server') == source['server'])), None)
                    if duplicate:
                        state = read_json(account_folder(DATA / 'profiles', duplicate['id']) / 'running.json', {})
                        if state.get('pid') and process_stamp(state['pid']) == state.get('stamp'):
                            raise ValueError('本工具中的对应账号正在运行，请先退出其游戏窗口再更新')
                    role, count = pinganzhi_sync.sync_account(prepare, DATA / 'profiles', game, source, servers)
                    old_id = duplicate['id'] if duplicate else None
                    if duplicate:
                        role['group'] = duplicate.get('group') or '未分组'
                    plans = {name: {**plan, 'roles': [role['id'] if key == old_id else key for key in plan.get('roles', [])], 'windows': {role['id'] if key == old_id else key: value for key, value in plan.get('windows', {}).items()}} for name, plan in config.get('layout_plans', {}).items()}
                    profiles = {role['id'] if key == old_id else key: value for key, value in config.get('window_profiles', {}).items()}
                    save({**config, 'layout_plans': plans, 'window_profiles': profiles, 'accounts': [a for a in config['accounts'] if a['id'] != old_id] + [role],
                          'pending': [a for a in config['pending'] if a['id'] != old_id], 'pinganzhi_root': root_var.get().strip()})
                    if old_id and tree.exists(old_id):
                        tree.delete(old_id)
                    refresh_row(role['id'], '已从平安志同步')
                    tree.selection_set(role['id'])
                    note(f'已同步 {role["nickname"]} · {role["server"]}，来源为该平安志账号，复制 {count} 个缓存文件。')
                    succeeded += 1
                except (OSError, ValueError) as error:
                    messagebox.showerror('同步未完成', f'{source["nickname"]}：{error}', parent=dialog)
            if succeeded:
                messagebox.showinfo('同步完成', f'已同步 {succeeded} 个所选平安志账号，可在列表中选择启动。', parent=dialog)
                dialog.destroy()
        ttk.Button(dialog, text='同步所选账号', command=accept_sync).pack(pady=12)
        refresh_sources()

    ttk.Button(toolbar, text='添加角色并登录', command=add_role).pack(side='left')
    ttk.Button(toolbar, text='从平安志同步', command=sync_pinganzhi).pack(side='left', padx=8)
    ttk.Button(toolbar, text='已登录，读取并确认', command=manual_read).pack(side='left', padx=8)
    ttk.Button(toolbar, text='暂停识别', command=pause).pack(side='left')
    ttk.Button(toolbar, text='启动所选角色', command=start_selected, style='Accent.TButton').pack(side='right')
    bottom = ttk.Frame(body)
    bottom.grid(row=5, column=0, sticky='ew', pady=(10, 0))
    def open_profile():
        selected = tree.selection()
        if selected:
            folder = account_folder(DATA / 'profiles', selected[0])
            if folder.is_dir():
                os.startfile(folder)
    ttk.Button(bottom, text='打开角色目录', command=open_profile).pack(side='left')
    note('自定义排列版 v8：勾选角色后启动；排列方案可保存角色选择、画面尺寸和屏幕。')
    note('只保存经你确认的昵称、区服及角色标识；旧登录记录不会自动绑定。')
    def poll():
        nonlocal busy, binding, next_read, previous_error
        for child, account_id in children[:]:
            if child.poll() is not None:
                if any(a['id'] == account_id for a in rows()):
                    refresh_row(account_id, '游戏已退出')
                children.remove((child, account_id))
                if binding == account_id:
                    binding = None
        while not results.empty():
            account_id, identity, error = results.get_nowait()
            busy = False
            next_read = time.monotonic() + 12
            if error:
                refresh_row(account_id, '等待登录；可点击重新读取')
                if error != previous_error:
                    note(error)
                    previous_error = error
                continue
            expected = find(account_id)
            if expected.get('target_short_id') and (expected['target_short_id'] != identity['short_id'] or expected.get('target_server_id') != identity['server_id']):
                refresh_row(account_id, '登录的不是目标角色，请切换后重新读取')
                note(f'所选目标是 {expected["nickname"]} · {expected["server"]}，当前登录角色不匹配，本次不保存。')
                continue
            binding = None
            if not identity['server_known']:
                label = simpledialog.askstring('确认区服名称', f'读取到区服编号 {identity["server_id"]}，本地区服表尚未收录。请填写游戏显示的区服名：', parent=window)
                if not label or not label.strip():
                    note('区服名称未确认，本次不保存。')
                    continue
                identity['server'] = label.strip()
            correct = messagebox.askyesno('确认角色信息',
                f'昵称：{identity["nickname"]}\n区服：{identity["server"]}（{identity["server_id"]}）\n\n这些信息是否正确？\n点击“是”后保存，今后可直接选中该角色启动。', parent=window)
            if correct:
                try:
                    save(role_reader.confirm_role(config, account_id, identity))
                    refresh_row(account_id, '角色已保存，可直接启动')
                    note(f'已保存：{identity["nickname"]} · {identity["server"]}')
                except (OSError, ValueError) as error:
                    messagebox.showerror('未保存', str(error))
            else:
                refresh_row(account_id, '信息未确认，可重新读取')
                note('本次信息未保存。可切换正确角色后点击“读取并确认”。')
        if binding and not busy and time.monotonic() >= next_read:
            next_read = float('inf')
            if current_version():
                begin_read(binding)
            else:
                binding = None
        window.after(500, poll)
    def tracked_state(account_id):
        return read_json(account_folder(DATA / 'profiles', account_id) / 'running.json', {})
    workspace = launcher_workspace.Workspace(window, left, right, toolbar, tree, lambda: config, save, tracked_state, process_stamp, note)
    poll()
    window.mainloop()
    instance_lock.close()


if __name__ == '__main__':
    main()
