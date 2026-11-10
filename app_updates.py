"""Fixed-repository update checks and verified downloads; never replaces app/data."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
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
        for asset in row.get('assets', []):
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


class UpdateManager:
    def __init__(self, root, brand):
        self.root = Path(root)
        self.brand = brand
        self.lock = threading.RLock()
        self.busy = False
        self.preferences = self.root / 'data' / 'update-preferences.json'
        try:
            self.auto = json.loads(self.preferences.read_text(encoding='utf-8')).get('auto_check', True) is True
        except (OSError, ValueError, AttributeError):
            self.auto = True
        self.state = {'phase': 'idle', 'message': '尚未检查更新', 'release': None, 'received': 0, 'total': 0, 'path': '', 'error': ''}

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
            if action == 'download' and not self.state['release']:
                raise ValueError('请先检查更新')
            self.busy = True
            self.state.update(phase='checking' if action == 'check' else 'downloading', message='正在连接 GitHub…', error='')
            if action == 'check':
                self.state.update(release=None, path='', received=0, total=0)
            threading.Thread(target=self._work, args=(action,), daemon=True).start()
        return self.status()

    def _work(self, action):
        try:
            if action == 'check':
                rows = None
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
                        break
                    except Exception:
                        continue
                if rows is None:
                    raise ValueError('无法读取版本信息')
                release = select_release(rows, self.brand['version'], self.brand.get('release_channel') == 'experimental')
                self._set(phase='available' if release else 'latest', release=release,
                          message='发现新版本' if release else '当前已是本更新通道的最新版本')
            else:
                self._download(copy.deepcopy(self.state['release']))
        except Exception:
            # Do not expose proxy credentials, signed redirect URLs or server details.
            self._set(phase='error', error='连接或校验失败，请检查网络后重试；也可打开 GitHub 发布页下载。', message='更新操作未完成')
        finally:
            with self.lock:
                self.busy = False

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
        self._set(received=0, total=release['size'], path='', message='正在下载并校验安装包…')
        with fetch(release['url']) as response, partial.open('xb') as output:
            while True:
                block = response.read(128 * 1024)
                if not block:
                    break
                received += len(block)
                if received > release['size'] or received > LIMIT:
                    raise ValueError('下载大小异常')
                output.write(block)
                digest.update(block)
                self._set(received=received)
        if received != release['size'] or digest.hexdigest() != release['sha256']:
            raise ValueError('安装包校验失败')
        partial.rename(target)
        self._set(phase='downloaded', message='下载完成，SHA-256 校验通过。请关闭游戏和启动器、备份 data 后按手册升级。', path=str(target))

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
