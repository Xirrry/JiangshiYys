"""Persistent, PID-bound read-only mystery shop inventory."""
from pathlib import Path
from contextlib import contextmanager
import json
import math
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
            db.execute('CREATE TABLE IF NOT EXISTS main_bonds (role_key TEXT PRIMARY KEY,payload TEXT,at REAL,error TEXT)')
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

    def main_settings(self, configured=(), keys=None, group_names=()):
        with self.connect() as db:
            row=db.execute("SELECT value FROM meta WHERE key='main_targets'").fetchone()
            saved=json.loads(row[0]) if row else []
            candidates={item['key']:item for item in saved}
            def add(server,short,name,group=None,order=None):
                if not str(server).isdigit() or not str(short).isdigit() or int(short)<=0:return
                key=str(int(server))+':'+str(int(short))
                candidates[key]={'key':key,'name':str(name or '角色'),'server':SERVERS.get(str(server),'区服 '+str(server)),'group':group or candidates.get(key,{}).get('group') or '未分组','order':order if order is not None else candidates.get(key,{}).get('order',999999)}
            for _,payload in db.execute('SELECT role_key,payload FROM roles'):
                data=json.loads(payload);role=data.get('role',{})
                add(role.get('server_id'),role.get('short_id'),role.get('name'))
                for key,bond in (data.get('bonds') or {}).items():
                    server,short=key.split(':');add(server,short,bond.get('name'))
            for order,role in enumerate(configured):add(role.get('server_id'),role.get('short_id'),role.get('nickname') or role.get('name'),role.get('group') or '未分组',order)
            groups=list(dict.fromkeys(['未分组',*group_names,*(item.get('group') or '未分组' for item in candidates.values())]))
            saved=[candidates.get(item['key'],item) for item in saved]
            if keys is not None:
                if not isinstance(keys,list) or len(keys)>100 or not all(isinstance(key,str) and key in candidates for key in keys):raise ValueError('请选择有效的大号角色')
                saved=[candidates[key] for key in dict.fromkeys(keys)]
                db.execute("INSERT OR REPLACE INTO meta VALUES('main_targets',?)",(json.dumps(saved,ensure_ascii=False),))
            bonds={key:{'bonds':json.loads(payload),'at':at,'error':error} for key,payload,at,error in db.execute('SELECT role_key,payload,at,error FROM main_bonds')}
            return {'main_targets':saved,'main_candidates':sorted(candidates.values(),key=lambda item:(groups.index(item.get('group') or '未分组'),item.get('order',999999),item['name'],item['key'])),'main_groups':groups,'main_bonds':bonds}

    def read_main_bonds(self, key):
        targets=self.main_settings()['main_targets']
        target=next((item for item in targets if item['key']==key),None)
        if not target:raise ValueError('请先保存大号设置')
        if not self.lock.acquire(blocking=False):raise ValueError('已有商店读取任务，请稍候')
        try:
            rows=sorted(self.windows(),key=lambda row:not row.get('title','').startswith(target['name']+' · '))
            selected=None
            for row in rows:
                try:
                    identity=bounty_transport.read(row['pid'],int(row['stamp']),self.app.process_stamp,DLL,128)
                    if self.identity(identity)==key:selected=row;break
                except Exception:continue
            if not selected:raise ValueError('该大号未登录，请先启动并进入庭院')
            data=bounty_transport.read(selected['pid'],int(selected['stamp']),self.app.process_stamp,DLL,64)
            if self.identity(data)!=key:raise ValueError('窗口已切换角色，未保存羁绊记录')
            bonds=data.get('bonds')
            if not isinstance(bonds,dict):raise ValueError('未读到好友羁绊，请打开大号好友列表后重试')
            clean={}
            for friend,entry in bonds.items():
                if isinstance(friend,str) and ((len(friend.split(':'))==2 and all(part.isdigit() for part in friend.split(':'))) or (friend.startswith('uid:') and friend[4:].isalnum() and len(friend)<=84)) and isinstance(entry,dict) and type(entry.get('level')) is int and 0<=entry['level']<=3:
                    clean[friend]={'name':str(entry.get('name','')),'level':entry['level']}
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO main_bonds VALUES(?,?,?,?)',(key,json.dumps(clean,ensure_ascii=False),time.time(),''))
            return self.load()
        except Exception as error:
            with self.connect() as db:db.execute("INSERT INTO main_bonds VALUES(?,'{}',0,?) ON CONFLICT(role_key) DO UPDATE SET error=excluded.error",(key,str(error)))
            raise
        finally:self.lock.release()

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
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds):
            raise ValueError('商店有效期数据无效，原有记录已保留')
        if seconds <= 0:
            raise ValueError('商店已过期或尚未开放，原记录保留在过期记录中；神秘商店每周三、周六开放')
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
