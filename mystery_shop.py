"""Persistent, PID-bound read-only mystery shop inventory."""
from pathlib import Path
from contextlib import contextmanager
import json
import sqlite3
import threading
import time

import bounty_transport
import role_reader
import window_layout

ROOT = Path(__file__).resolve().parent
DLL = ROOT / 'hardware/shop-reader/shop_agent.dll'
SERVERS = {str(row['id']): row['name'] for row in json.loads((ROOT / 'servers.json').read_text('utf-8'))['servers']}


class ShopStore:
    def __init__(self, data_root, app):
        self.app = app
        self.lock = threading.Lock()
        self.database = Path(data_root) / 'data/mystery-shop.sqlite3'
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS roles (role_key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        # Import the experimental page once, only in its original source workspace.
        legacy = ROOT / 'experiments/mystery-shop/shop-cache.json'
        if Path(data_root).resolve() == ROOT.resolve() and legacy.is_file():
            with self.connect() as db:
                if not db.execute("SELECT 1 FROM meta WHERE key='experiment_import'").fetchone():
                    document = json.loads(legacy.read_text('utf-8'))
                    for data in document.get('roles', {}).values():
                        key = self.identity(data)
                        if any(s.get('goods') for s in data.get('shops', [])):
                            db.execute('INSERT OR IGNORE INTO roles VALUES(?,?)', (key, json.dumps(data, ensure_ascii=False)))
                    db.execute("INSERT INTO meta VALUES('experiment_import','1')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def identity(document):
        role = document.get('role', {})
        server, short = str(role.get('server_id', '')), str(role.get('short_id', ''))
        if not server.isdigit() or not short.isdigit() or int(short) <= 0:
            raise ValueError('尚未读到有效角色身份，请先登录进入庭院')
        return server + ':' + short

    def load(self):
        with self.connect() as db:
            roles = {key: json.loads(value) for key, value in db.execute('SELECT role_key,payload FROM roles ORDER BY role_key')}
        return {'roles': roles, 'errors': []}

    def windows(self):
        return window_layout.running_game_windows(role_reader.game_pids(), self.app.process_stamp)

    def save(self, document, captured_at=None):
        key = self.identity(document)
        if not isinstance(document.get('shops'), list) or not any(shop.get('goods') for shop in document['shops']):
            raise ValueError('未读到商品，原有记录已保留；请在游戏中打开神秘商店后重试')
        # Own the serialized copy; never mutate the caller's result.
        data = json.loads(json.dumps(document, ensure_ascii=False))
        now = time.time() if captured_at is None else captured_at
        seconds = data.get('seconds_left')
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise ValueError('商店有效期数据无效，原有记录已保留')
        data['role']['server'] = SERVERS.get(str(data['role']['server_id']), '未知区服')
        data.update(captured_at=now, expires_at=now + max(0, seconds))
        with self.connect() as db:
            db.execute('INSERT INTO roles VALUES(?,?) ON CONFLICT(role_key) DO UPDATE SET payload=excluded.payload',
                       (key, json.dumps(data, ensure_ascii=False)))

    def read(self, target='all'):
        if not self.lock.acquire(blocking=False):
            raise ValueError('神秘商店读取正在进行，请稍候')
        try:
            windows = self.windows()
            if target != 'all':
                windows = [window for window in windows if window['id'] == target]
            if not windows:
                raise ValueError('未找到目标游戏窗口，请刷新窗口列表')
            errors, successes = [], 0
            for window in windows:
                try:
                    captured = time.time()
                    data = bounty_transport.read(window['pid'], int(window['stamp']), self.app.process_stamp, DLL, 32)
                    self.save(data, captured)
                    successes += 1
                except Exception as error:
                    errors.append({'window': window.get('title') or '游戏窗口', 'message': str(error)})
            result = self.load()
            result.update(errors=errors, successes=successes)
            return result
        finally:
            self.lock.release()
