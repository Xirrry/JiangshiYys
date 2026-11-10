"""Copy one selected Pinganzhi account profile, never the global game cache."""
import json
import os
from pathlib import Path
import shutil
import uuid
import role_reader


def default_root():
    return Path(os.environ['APPDATA']) / 'com.yys.analysis/desktop-accounts'


def safe_directory(path):
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise ValueError(f'账号目录不是独立目录：{path.name}')


def manifest(root):
    safe_directory(root)
    found = {}
    stack = [root]
    while stack:
        directory = stack.pop()
        for file in directory.iterdir():
            if file.is_symlink() or file.is_junction():
                raise ValueError('登录缓存包含链接，已停止同步')
            if file.is_dir():
                stack.append(file)
            elif file.is_file():
                stat = file.stat()
                found[str(file.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return found


def scan_accounts(root):
    root = Path(root)
    safe_directory(root)
    result = []
    for directory in root.iterdir():
        if directory.name == 'recycle' or not directory.is_dir() or directory.is_junction() or directory.is_symlink():
            continue
        try:
            meta = json.loads((directory / 'account.json').read_text(encoding='utf-8'))
            if meta.get('id') != directory.name or meta.get('recycled') or not meta.get('ready'):
                continue
            profile = directory / 'profile'
            config_file = profile / 'game/Documents/clientconfig'
            cache = profile / 'AppData/Roaming/Netease/Mpay'
            if not config_file.is_file() or not cache.is_dir():
                continue
            result.append({'directory': directory, 'meta': meta, 'cache': cache,
                           'config_file': config_file, 'nickname': str(meta.get('nickname') or directory.name),
                           'server': str(meta.get('server') or meta.get('channelServer') or '未知区服')})
        except (OSError, ValueError, TypeError):
            continue
    return sorted(result, key=lambda a: (a['nickname'], a['server']))


def ensure_source_idle(meta):
    pid = meta.get('processId')
    if pid and int(pid) in role_reader.game_pids():
        raise ValueError('此平安志账号仍在运行，请正常退出该游戏窗口后同步')
    if meta.get('running') and not pid:
        raise ValueError('无法确认此平安志账号是否已退出，请退出其游戏窗口后重试')


def sync_account(prepare_fn, base, game, source, servers):
    directory = source['directory']
    safe_directory(directory)
    if (directory / 'account.json').is_symlink():
        raise ValueError('账号资料不能是链接')
    # Re-read instead of trusting the scan snapshot.
    meta = json.loads((directory / 'account.json').read_text(encoding='utf-8'))
    if meta.get('id') != directory.name or meta.get('recycled') or not meta.get('ready'):
        raise ValueError('平安志账号状态已变化，请刷新列表')
    ensure_source_idle(meta)
    for relative in ('profile', 'profile/AppData', 'profile/AppData/Roaming',
                     'profile/AppData/Roaming/Netease', 'profile/AppData/Roaming/Netease/Mpay',
                     'profile/game', 'profile/game/Documents'):
        safe_directory(directory / relative)
    cache = directory / 'profile/AppData/Roaming/Netease/Mpay'
    before = manifest(cache)
    if not any(Path(name).suffix.lower() == '.db' for name in before):
        raise ValueError('此账号没有可同步的登录数据库')
    original_file = directory / 'profile/game/Documents/clientconfig'
    if original_file.is_symlink():
        raise ValueError('角色配置不能是链接')
    original_bytes = original_file.read_bytes()
    original = role_reader.read_client_config(original_file)
    account_id = uuid.uuid4().hex
    profile, cwd, env = prepare_fn(base, game, account_id)
    target = profile / 'AppData/Roaming/Netease/Mpay'
    if any(target.iterdir()):
        raise ValueError('新建的目标缓存不是空目录，停止同步')
    copied = 0
    for relative in before:
        # Logs and audio are not login state.
        if Path(relative).suffix.lower() in ('.log', '.wav'):
            continue
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with (cache / relative).open('rb') as src, dest.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        copied += 1
    if manifest(cache) != before or original_file.read_bytes() != original_bytes:
        raise ValueError('来源账号数据正在变化，本次不登记，请退出游戏后重试')
    ensure_source_idle(meta)
    (cwd / 'Documents/clientconfig').write_bytes(original_bytes)
    server_id = str(original.get('areaSetId') or '')
    nickname = str(meta.get('nickname') or source['nickname'])
    server = str(meta.get('server') or source['server'])
    matches = [r for r in role_reader.historical_roles(original)
               if str(r.get('server_id')) == server_id and r.get('player_name') == nickname]
    identity = {'nickname': nickname, 'server': server, 'server_id': server_id, 'server_known': True}
    if len(matches) == 1:
        identity['short_id'] = str(matches[0]['player_id'])
    role = {'id': account_id, 'name': nickname, **identity, 'confirmed': True,
            'cache_mode': 'pinganzhi-account', 'pinganzhi_source_id': meta['id'],
            'pinganzhi_source_root': str(directory.parent.resolve()), 'synced_at': __import__('time').time()}
    return role, copied
