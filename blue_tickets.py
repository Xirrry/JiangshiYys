"""Local role-based drop ledger. No orders, remote APIs, or seeded records."""
import copy
import datetime as dt
import json
from pathlib import Path
import sqlite3
import threading

STATES = {'recorded', 'pending', 'unknown', 'not_played'}
FIELDS = ('first', 'second', 'blue', 'fragments', 'eggs')

def validate(row, today=None):
    if not isinstance(row, dict):
        raise ValueError('记录格式无效')
    date = row.get('date')
    try:
        if not isinstance(date, str) or dt.date.fromisoformat(date).isoformat() != date:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('日期无效')
    if date > (today or dt.date.today().isoformat()):
        raise ValueError('不能记录未来掉落')
    mode = row.get('mode')
    if mode not in {'daily', 'xiajian'}:
        raise ValueError('掉落来源无效')
    if mode == 'xiajian' and dt.date.fromisoformat(date).weekday() not in (4, 5, 6):
        raise ValueError('狭间仅限周五、周六、周日')
    values = {}
    for field in FIELDS:
        value = row.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 1000000):
            raise ValueError('数量必须为 0–1000000 的整数，或留空')
        values[field] = value
    if mode == 'daily' and any(values[f] is not None for f in ('blue', 'fragments', 'eggs')) or mode == 'xiajian' and any(values[f] is not None for f in ('first', 'second')):
        raise ValueError('不同来源的产出不能混填')
    for field in ('first', 'second'):
        state = row.get(field + 'State', 'recorded' if values[field] is not None else 'pending')
        if state not in STATES or (state == 'recorded') != (values[field] is not None) or (mode == 'xiajian' and state != 'pending'):
            raise ValueError('次数状态与数量不一致')
        values[field + 'State'] = state
    note = row.get('note', '')
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError('备注最多 500 字')
    remove = row.get('remove', False)
    if type(remove) is not bool:
        raise ValueError('撤销标记无效')
    empty = all(values[f] is None for f in FIELDS) and all(values[f + 'State'] == 'pending' for f in ('first', 'second')) and not note.strip()
    if empty and not remove:
        raise ValueError('空记录不能保存；数量为 0 时请明确填写 0')
    return {'role_id': row.get('role_id'), 'date': date, 'mode': mode, **values, 'note': note.strip(), 'remove': remove}


class BlueStore:
    def __init__(self, root):
        self.file = Path(root) / 'data' / 'blue-tickets.sqlite3'
        self.lock = threading.RLock()

    def _connect(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        if self.file.is_symlink() or self.file.is_junction():
            raise ValueError('蓝票数据库不能是链接')
        connection = sqlite3.connect(self.file, timeout=8)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
          CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
          INSERT OR IGNORE INTO meta VALUES(1,0);
          CREATE TABLE IF NOT EXISTS subjects(role_id TEXT PRIMARY KEY, label TEXT NOT NULL, server TEXT NOT NULL, selected INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS records(role_id TEXT NOT NULL, date TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(role_id,date));
          CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, role_id TEXT NOT NULL, date TEXT NOT NULL, before_json TEXT, after_json TEXT, changed_at TEXT NOT NULL);
        """)
        return connection

    @staticmethod
    def _roles(roles):
        return {r['id']: {'id': r['id'], 'label': str(r.get('nickname') or r.get('name') or '未命名角色'), 'server': str(r.get('server') or ''), 'active': True} for r in roles}

    def _load(self, db, roles):
        if not db.in_transaction:
            db.execute('BEGIN')
        current = self._roles(roles)
        subjects = {r['role_id']: dict(r) for r in db.execute('SELECT * FROM subjects')}
        with_records = {r[0] for r in db.execute('SELECT DISTINCT role_id FROM records')}
        result = []
        for key in dict.fromkeys([*current, *subjects]):
            old = subjects.get(key, {})
            role = current.get(key, {'id': key, 'label': old.get('label', '历史角色'), 'server': old.get('server', ''), 'active': False})
            result.append({**role, 'selected': bool(old.get('selected')) and key in current, 'has_records': key in with_records})
        return {'revision': db.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0], 'roles': result,
                'records': [json.loads(row[0]) for row in db.execute('SELECT payload FROM records ORDER BY date,role_id')]}

    def load(self, roles):
        with self.lock:
            db = self._connect()
            try:
                db.execute('BEGIN')
                return self._load(db, roles)
            finally:
                db.rollback()
                db.close()

    def _revision(self, db, value):
        if type(value) is not int or value != db.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0]:
            raise ValueError('蓝票数据已变化，输入已保留；请关闭编辑后刷新核对，再重试')

    def subjects(self, ids, revision, roles):
        current = self._roles(roles)
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(key not in current for key in ids):
            raise ValueError('参与角色列表无效，请刷新后选择')
        with self.lock:
            db = self._connect()
            try:
                db.execute('BEGIN IMMEDIATE'); self._revision(db, revision)
                db.execute('UPDATE subjects SET selected=0')
                for key in ids:
                    r = current[key]
                    db.execute('INSERT INTO subjects VALUES(?,?,?,1) ON CONFLICT(role_id) DO UPDATE SET label=excluded.label, server=excluded.server, selected=1', (key, r['label'], r['server']))
                db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
                result = self._load(db, roles)
                db.commit()
                return result
            finally:
                db.close()

    def save(self, rows, revision, allow_replace, roles):
        if not isinstance(rows, list) or not 1 <= len(rows) <= 200 or type(allow_replace) is not bool:
            raise ValueError('一次可保存 1–200 条记录')
        valid = [validate(r) for r in rows]
        keys = [(r['role_id'], r['date']) for r in valid]
        if len(keys) != len(set(keys)):
            raise ValueError('同一角色同日不能重复提交')
        current = self._roles(roles)
        with self.lock:
            db = self._connect()
            try:
                db.execute('BEGIN IMMEDIATE'); self._revision(db, revision)
                selected = {r[0] for r in db.execute('SELECT role_id FROM subjects WHERE selected=1')}
                for r in valid:
                    key, date = r['role_id'], r['date']
                    if key not in current or key not in selected:
                        raise ValueError('只能编辑已选择参与蓝票记录的现有角色')
                    old = db.execute('SELECT payload FROM records WHERE role_id=? AND date=?', (key, date)).fetchone()
                    before = json.loads(old[0]) if old else None
                    after = {k: v for k, v in r.items() if k != 'remove'}
                    if before and before['mode'] != r['mode'] and not r['remove'] and not allow_replace:
                        raise ValueError('同角色同日只能保留一种来源，请确认替换')
                    if r['remove']:
                        if before and before['mode'] != r['mode']:
                            raise ValueError('记录来源已变化，请刷新')
                        after = None
                    if before == after:
                        continue
                    if after is None:
                        db.execute('DELETE FROM records WHERE role_id=? AND date=?', (key, date))
                    else:
                        db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload', (key, date, json.dumps(after, ensure_ascii=False)))
                    role = current[key]
                    db.execute('UPDATE subjects SET label=?,server=? WHERE role_id=?', (role['label'], role['server'], key))
                    db.execute('INSERT INTO history(role_id,date,before_json,after_json,changed_at) VALUES(?,?,?,?,?)', (key, date, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), dt.datetime.now().isoformat(timespec='seconds')))
                db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
                result = self._load(db, roles)
                db.commit()
                return result
            except Exception:
                db.rollback(); raise
            finally:
                db.close()

    def history(self, role_id, date):
        if not isinstance(role_id, str) or not isinstance(date, str):
            raise ValueError('历史查询无效')
        with self.lock:
            db = self._connect()
            try:
                return [dict(r) for r in db.execute('SELECT id,before_json,after_json,changed_at FROM history WHERE role_id=? AND date=? ORDER BY id DESC LIMIT 100', (role_id,date))]
            finally:
                db.close()
