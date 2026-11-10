"""Fixed-repository update checks and verified downloads; never replaces app/data."""
import copy
import hashlib
import json
import os
import shutil
import stat
import zipfile
import uuid
from pathlib import Path
import re
import threading
import time
import socket
import urllib.error
import urllib.parse
import urllib.request

REPO = 'Xirrry/JiangshiYys'
API = 'https://api.github.com/repos/' + REPO + '/releases?per_page=30'
PAGE = 'https://github.com/' + REPO + '/releases'
MANIFEST = 'https://raw.githubusercontent.com/' + REPO + '/main/updates.json'
LIMIT = 256 * 1024 * 1024


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?(?:-experimental)?', str(value))
    if not match:
        raise ValueError('不支持的版本号')
    return tuple(int(x or 0) for x in match.groups())


def trusted_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('更新地址不可信')
    if url == MANIFEST:
        return url
    if u.hostname == 'api.github.com' and u.path.startswith('/repos/' + REPO + '/releases'):
        return url
    if u.hostname == 'github.com' and u.path.startswith('/' + REPO + '/releases'):
        return url
    if u.hostname in {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
        return url
    raise ValueError('更新地址不可信')


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    trusted_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'JiangshiYys-Updater', 'Accept': 'application/vnd.github+json'})
    return urllib.request.build_opener(Redirects()).open(req, timeout=20)


def select_release(rows, current, experimental):
    current_version = version(current)
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get('draft') or (row.get('prerelease') and not experimental):
            continue
        try:
            parsed = version(row.get('tag_name', ''))
        except ValueError:
            continue
        # Same-number stable release may replace an experimental build.
        if parsed < current_version or (parsed == current_version and not (experimental and not row.get('prerelease'))):
            continue
        number = row['tag_name'].removeprefix('v').removesuffix('-experimental')
        allowed = {f'JiangshiYys-{number}-win-x64.zip', f'JiangshiYys-{number}-experimental-win-x64.zip'}
        assets = row.get('assets')
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            digest = asset.get('digest') or ''
            name = asset.get('name', '')
            url = asset.get('browser_download_url', '')
            expected = 'https://github.com/' + REPO + '/releases/download/' + row['tag_name'] + '/' + name
            size = asset.get('size')
            if name not in allowed or url != expected or not isinstance(size, int) or not 0 < size <= LIMIT:
                continue
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                continue
            candidates.append((parsed, not row.get('prerelease'), {'version': number, 'tag': row['tag_name'], 'name': name,
                'url': url, 'page': PAGE + '/tag/' + row['tag_name'], 'size': size, 'sha256': digest[7:],
                'notes': str(row.get('body') or '')[:8000], 'experimental': bool(row.get('prerelease'))}))
    return max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else None


class Cancelled(Exception):
    pass


class UpdateFailure(Exception):
    pass


def failure_message(error):
    if isinstance(error, UpdateFailure):
        return str(error)
    if isinstance(error, urllib.error.HTTPError):
        if error.code in (403, 429):
            return '更新服务限流或拒绝访问，请稍后重试，或打开 GitHub 发布页下载。'
        if error.code == 404:
            return '更新文件暂不可用，请稍后重新检查更新。'
        return '更新服务暂时异常，请稍后重试，或打开 GitHub 发布页下载。'
    if isinstance(error, (TimeoutError, socket.timeout)) or (isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError)):
        return '连接超时，请检查网络后重试，或打开 GitHub 发布页下载。'
    if isinstance(error, OSError) and error.errno == 28:
        return '下载目录磁盘空间不足，请释放空间后重试。'
    if isinstance(error, PermissionError):
        return '无法写入下载目录，请检查软件目录的写入权限。'
    return '连接或读取失败，请检查网络后重试；也可打开 GitHub 发布页下载。'


class UpdateManager:
    def __init__(self, root, brand):
        self.root = Path(root)
        self.brand = brand
        self.lock = threading.RLock()
        self.busy = False
        self.cancel_event = threading.Event()
        self.install_callback = None
        self.install_failed = None
        self.preferences = self.root / 'data' / 'update-preferences.json'
        try:
            self.auto = json.loads(self.preferences.read_text(encoding='utf-8')).get('auto_check', True) is True
        except (OSError, ValueError, AttributeError):
            self.auto = True
        self.state = {'phase': 'idle', 'message': '尚未检查更新', 'release': None, 'received': 0, 'total': 0, 'path': '', 'error': '', 'checked_at': '', 'source': '', 'speed': 0, 'cancel_pending': False}

    def status(self):
        with self.lock:
            return {**copy.deepcopy(self.state), 'auto_check': self.auto, 'current': self.brand['version']}

    def _set(self, **values):
        with self.lock:
            self.state.update(values)

    def settings(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('更新设置无效')
        with self.lock:
            self.preferences.parent.mkdir(parents=True, exist_ok=True)
            self.preferences.write_text(json.dumps({'auto_check': enabled}), encoding='utf-8')
            self.auto = enabled
        return self.status()

    def start(self, action):
        with self.lock:
            if self.busy:
                return self.status()
            if action in ('download', 'download_install', 'install') and not self.state['release']:
                raise ValueError('请先检查更新')
            self.busy = True
            self.cancel_event.clear()
            self.state.update(cancel_pending=False, speed=0)
            self.state.update(phase='checking' if action == 'check' else 'installing' if action == 'install' else 'downloading', message='正在连接 GitHub…', error='')
            if action == 'check':
                self.state.update(release=None, path='', received=0, total=0)
            threading.Thread(target=self._work, args=(action,), daemon=True).start()
        return self.status()

    def _work(self, action):
        try:
            if action == 'check':
                rows = None
                last_error = None
                source_label = ''
                for source in (MANIFEST, API):
                    try:
                        with fetch(source) as response:
                            content = response.read(2 * 1024 * 1024 + 1)
                        if len(content) > 2 * 1024 * 1024:
                            raise ValueError('版本信息过大')
                        candidate = json.loads(content)
                        if not isinstance(candidate, list):
                            raise ValueError('版本信息格式异常')
                        rows = candidate
                        source_label = '公开更新清单' if source == MANIFEST else 'GitHub Releases'
                        break
                    except Exception as error:
                        last_error = error
                        continue
                if rows is None:
                    raise last_error or ValueError('无法读取版本信息')
                release = select_release(rows, self.brand['version'], self.brand.get('release_channel') == 'experimental')
                self._set(phase='available' if release else 'latest', release=release, checked_at=time.strftime('%Y-%m-%d %H:%M:%S'), source=source_label,
                          message='发现新版本' if release else '当前已是本更新通道的最新版本')
            elif action in ('download', 'download_install'):
                self._download(copy.deepcopy(self.state['release']))
                if action == 'download_install':
                    self._install(copy.deepcopy(self.state['release']))
            elif action == 'install':
                self._install(copy.deepcopy(self.state['release']))
            else:
                raise ValueError('不支持的更新操作')
        except Cancelled:
            self._set(phase='cancelled', message='下载已取消，可重新下载。不完整文件不会用于升级。', error='', path='', speed=0)
        except Exception as error:
            # Never reveal proxy credentials or signed redirect URLs.
            self._set(phase='error', error=failure_message(error), message='更新操作未完成', speed=0)
        finally:
            with self.lock:
                self.busy = False
                self.state['cancel_pending'] = False
            if action in ('download_install', 'install') and self.state['phase'] != 'restarting' and self.install_failed:
                self.install_failed()

    def cancel(self):
        with self.lock:
            if self.busy and self.state['phase'] == 'downloading':
                self.cancel_event.set()
                self.state.update(cancel_pending=True, message='正在取消下载…')
        return self.status()

    def _download(self, release):
        import uuid
        folder = self.root / 'update-downloads'
        folder.mkdir(exist_ok=True)
        if folder.is_symlink() or folder.is_junction():
            raise ValueError('下载目录不可重定向')
        target = folder / (uuid.uuid4().hex[:12] + '-' + release['name'])
        partial = target.with_suffix('.zip.part')
        digest = hashlib.sha256()
        received = 0
        started = time.monotonic()
        self._set(received=0, total=release['size'], path='', message='正在下载并校验安装包…')
        with fetch(release['url']) as response, partial.open('xb') as output:
            while True:
                if self.cancel_event.is_set():
                    raise Cancelled()
                block = response.read(128 * 1024)
                if not block:
                    break
                received += len(block)
                if received > release['size'] or received > LIMIT:
                    raise UpdateFailure('下载大小与发布信息不符，已停止；请重新检查更新。')
                output.write(block)
                digest.update(block)
                self._set(received=received, speed=round(received / max(0.1, time.monotonic() - started)))
        if self.cancel_event.is_set():
            raise Cancelled()
        if received != release['size'] or digest.hexdigest() != release['sha256']:
            raise UpdateFailure('安装包完整性校验失败，文件不会用于升级，请重新下载。')
        partial.rename(target)
        self._set(phase='downloaded', message='下载完成，SHA-256 校验通过。请关闭游戏和启动器、备份 data 后按手册升级。', path=str(target), speed=0)

    def _install(self, release):
        self._set(phase='installing', message='正在核验并准备自动安装，请勿关闭程序…')
        source = Path(self.state['path']) if self.state['path'] else None
        folder = self.root / 'update-downloads'
        if source is None or source.parent != folder or not source.is_file() or source.is_symlink():
            raise UpdateFailure('没有已校验的安装包，请先下载新版。')
        if source.stat().st_size != release['size'] or hashlib.sha256(source.read_bytes()).hexdigest() != release['sha256']:
            raise UpdateFailure('安装包已变化，请重新下载后安装。')
        helper = self.root / 'ApplyUpdate.exe'
        if not helper.is_file() or not callable(self.install_callback):
            raise UpdateFailure('当前版本缺少自动安装组件，请打开发布页手动升级。')
        if self.root.is_symlink() or self.root.is_junction():
            raise UpdateFailure('当前安装目录被重定向，请手动升级。')
        job = self.root.parent / ('.JiangshiYys-update-' + uuid.uuid4().hex)
        fresh = job / 'new'
        prefix = release['name'][:-4]
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            total = sum(item.file_size for item in entries)
            if len(entries) > 20000 or total > 700 * 1024 * 1024:
                raise UpdateFailure('安装包解压大小异常，请手动升级。')
            if shutil.disk_usage(self.root.parent).free < total + 64 * 1024 * 1024:
                raise UpdateFailure('磁盘空间不足，无法准备新版本。')
            seen = set()
            for item in entries:
                parts = item.filename.split('/')
                clean = parts[:-1] if item.is_dir() else parts
                if not clean or clean[0] != prefix or any(not p or p in ('.', '..') or ':' in p or chr(92) in p or p.rstrip(' .') != p for p in clean):
                    raise UpdateFailure('安装包包含不安全路径，已停止安装。')
                if stat.S_ISLNK(item.external_attr >> 16) or (len(clean) > 1 and clean[1].casefold() in {'data', 'update-downloads'}):
                    raise UpdateFailure('安装包包含链接或私人数据目录，已停止安装。')
                key = '/'.join(clean).casefold()
                if key in seen:
                    raise UpdateFailure('安装包存在重复文件路径。')
                seen.add(key)
            fresh.mkdir(parents=True, exist_ok=False)
            for item in entries:
                relative = Path(*item.filename.split('/')[1:])
                destination = fresh / relative
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as incoming, destination.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
        new_brand = json.loads((fresh / 'brand.json').read_text(encoding='utf-8'))
        if new_brand.get('version') != release['version'] or new_brand.get('name') != self.brand.get('name'):
            raise UpdateFailure('安装包的软件或版本信息不匹配。')
        for name in ['僵尸痒痒鼠.exe', 'yys_core.pyd', 'runtime/pythonw.exe', 'frontend/dist/index.html']:
            if not (fresh / name).is_file():
                raise UpdateFailure('安装包缺少运行文件，已停止安装。')
        shutil.copy2(helper, job / 'ApplyUpdate.exe')
        self._set(phase='restarting', message='即将关闭并安装，完成后自动重新打开。旧版文件保留在更新备份目录。')
        self.install_callback(job)

    def open_page(self):
        import webbrowser
        webbrowser.open(PAGE)
        return self.status()

    def open_download(self):
        with self.lock:
            path = Path(self.state['path']) if self.state['path'] else None
        if path is None or path.parent != self.root / 'update-downloads' or not path.is_file():
            raise ValueError('尚无已校验的下载文件')
        subprocess = __import__('subprocess')
        subprocess.Popen(['explorer.exe', '/select,', str(path)])
        return self.status()
