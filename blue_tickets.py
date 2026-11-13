"""Local role-based drop ledger. No orders, remote APIs, or seeded records."""
import copy
import hashlib
import datetime as dt
import json
from pathlib import Path
import sqlite3
import threading
import server_merges

# Visible dojo receipts must contain at least one actual reward.
MAIL_REWARD_FILTER = "json_extract(payload,'$.type') != 400175 AND EXISTS (SELECT 1 FROM json_each(payload,'$.items') reward WHERE json_extract(reward.value,'$[1]') > 0)"

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
          CREATE TABLE IF NOT EXISTS mail_archives(scope TEXT PRIMARY KEY,archive_id TEXT UNIQUE NOT NULL,label TEXT NOT NULL,server TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS resource_meta(item_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS resource_names(item_id TEXT PRIMARY KEY,name TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS mail_rewards(scope TEXT NOT NULL, uid TEXT NOT NULL, role_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope,uid));
          CREATE TABLE IF NOT EXISTS mail_derived(role_id TEXT NOT NULL,date TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(role_id,date));
          CREATE TABLE IF NOT EXISTS blue_role_redirects(source_id TEXT PRIMARY KEY,target_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, role_id TEXT NOT NULL, date TEXT NOT NULL, before_json TEXT, after_json TEXT, changed_at TEXT NOT NULL);
        """)
        return connection

    @staticmethod
    def _roles(roles):
        return {r['id']: {'id': r['id'], 'label': str(r.get('nickname') or r.get('name') or '未命名角色'), 'server': str(r.get('server') or ''), 'active': True} for r in roles}

    def _blue_roles(self, db, roles):
        current=self._roles(roles)
        redirects=dict(db.execute('SELECT source_id,target_id FROM blue_role_redirects'))
        recorded={r[0] for r in db.execute('SELECT DISTINCT role_id FROM records')}
        for row in db.execute(f'SELECT * FROM mail_archives WHERE scope IN (SELECT scope FROM mail_rewards WHERE {MAIL_REWARD_FILTER})'):
            matches=server_merges.matches(row['scope'],roles)
            if row['archive_id'] in redirects or (len(matches)==1 and row['archive_id'] not in recorded):continue
            current[row['archive_id']]={'id':row['archive_id'],'label':row['label'],'server':row['server'],'active':True}
        for target in redirects.values():
            if target not in current:
                row=db.execute('SELECT label,server FROM subjects WHERE role_id=?',(target,)).fetchone()
                if row:current[target]={'id':target,'label':row['label'],'server':row['server'],'active':True}
        return current

    def _redirect_blue_role(self, db, source, target, label, server):
        if source==target:return False,[]
        warnings=[];copies=[]
        for row in db.execute('SELECT date,payload FROM records WHERE role_id=?',(source,)):
            before=db.execute('SELECT payload FROM records WHERE role_id=? AND date=?',(target,row['date'])).fetchone()
            derived=db.execute('SELECT payload FROM mail_derived WHERE role_id=? AND date=?',(source,row['date'])).fetchone()
            auto=bool(derived and derived[0]==row['payload'])
            old_derived=db.execute('SELECT payload FROM mail_derived WHERE role_id=? AND date=?',(target,row['date'])).fetchone()
            old_auto=bool(before and old_derived and before[0]==old_derived[0])
            if not before and old_derived:continue
            after=json.loads(row['payload']);after['role_id']=target;payload=json.dumps(after,ensure_ascii=False)
            if before and not auto and not old_auto and json.loads(before[0])!=after:
                warnings.append(label+' · '+row['date']+'：合区前后存在不同手动记录，保留两份待核对');continue
            if not before or (not auto and old_auto):copies.append((row['date'],payload,auto,before[0] if before else 'null'))
        if warnings:return False,warnings
        for date,payload,auto,before in copies:
            db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(target,date,payload))
            if auto:db.execute('INSERT INTO mail_derived VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(target,date,payload))
            db.execute('INSERT INTO history(role_id,date,before_json,after_json,changed_at) VALUES(?,?,?,?,?)',(target,date,before,payload,dt.datetime.now().isoformat(timespec='seconds')))
        # Retain a manually removed automatic record's marker, so merge cannot revive it.
        for row in db.execute('SELECT date,payload FROM mail_derived WHERE role_id=?',(source,)):
            if db.execute('SELECT 1 FROM records WHERE role_id=? AND date=?',(source,row['date'])).fetchone():continue
            after=json.loads(row['payload']);after['role_id']=target
            db.execute('INSERT OR IGNORE INTO mail_derived VALUES(?,?,?)',(target,row['date'],json.dumps(after,ensure_ascii=False)))
        old=db.execute('SELECT target_id FROM blue_role_redirects WHERE source_id=?',(source,)).fetchone()
        db.execute('INSERT INTO blue_role_redirects VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET target_id=excluded.target_id',(source,target))
        selected=db.execute('SELECT MAX(selected) FROM subjects WHERE role_id IN (?,?)',(source,target)).fetchone()[0]
        db.execute('INSERT INTO subjects VALUES(?,?,?,?) ON CONFLICT(role_id) DO UPDATE SET label=excluded.label,server=excluded.server,selected=MAX(subjects.selected,excluded.selected)',(target,label,server,1 if selected is None else selected))
        db.execute('UPDATE subjects SET selected=0 WHERE role_id=?',(source,))
        return bool(copies or not old or old[0]!=target),[]

    def _project_mail_blue(self, db, roles, scopes=None):
        synced=0;warnings=[];grouped={};redirected=False
        archives=db.execute(f'SELECT * FROM mail_archives WHERE scope IN (SELECT scope FROM mail_rewards WHERE {MAIL_REWARD_FILTER})').fetchall()
        # All aliases of a merged server are grouped before deriving daily slots.
        redirects=dict(db.execute('SELECT source_id,target_id FROM blue_role_redirects'))
        def resolved(key):
            visited=set()
            while key in redirects:
                if key in visited:raise ValueError('角色合区映射存在循环，未保存')
                visited.add(key);key=redirects[key]
            return key
        representatives={}
        for archive in sorted(archives,key=lambda r:r['scope']):
            server,short=archive['scope'].split(':',1)
            representatives.setdefault(server_merges.canonical(server)+':'+short,resolved(archive['archive_id']))
        for archive in archives:
            scope=archive['scope'];matches=server_merges.matches(scope,roles)
            server,short=scope.split(':',1)
            target=matches[0] if len(matches)==1 else None
            key=target['id'] if target else representatives[server_merges.canonical(server)+':'+short]
            label=str(target.get('nickname') or target.get('name')) if target else archive['label']
            display_server=target.get('server','') if target else archive['server']
            previous=resolved(archive['archive_id'])
            if previous!=archive['archive_id'] and previous!=key:
                changed,notes=self._redirect_blue_role(db,previous,key,label,display_server);warnings.extend(notes);redirected|=changed
                if notes:key=previous
            if key!=archive['archive_id']:
                changed,notes=self._redirect_blue_role(db,archive['archive_id'],key,label,display_server);warnings.extend(notes);redirected|=changed
                if notes:key=archive['archive_id'];label=archive['label'];display_server=archive['server']
            group=grouped.setdefault(key,{'label':label,'server':display_server,'scopes':set(),'mails':{}});group['scopes'].add(scope)
            for row in db.execute(f'SELECT payload FROM mail_rewards WHERE scope=? AND {MAIL_REWARD_FILTER}',(scope,)):
                mail=json.loads(row[0]);old=group['mails'].get(mail['uid'])
                if old and old!=mail:
                    warnings.append(label+'：合区档案存在同邮件不同内容，保留原始邮件并跳过自动回填');group['conflict']=True
                else:group['mails'][mail['uid']]=mail
        for key,group in grouped.items():
            if scopes is not None and not scopes.intersection(group['scopes']):continue
            if group.get('conflict'):continue
            daily={}
            for mail in group['mails'].values():
                if mail['type']==400179:daily.setdefault(mail['date'],[]).append(mail)
            for date,items in sorted(daily.items()):
                prefix=group['label']+' · '+date+'：'
                if len(items)>2:
                    warnings.append(prefix+'超过两封场次邮件，蓝票页未自动合并，请手动核对');continue
                if date>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat():continue
                items.sort(key=lambda m:(m['time'],m['uid']))
                before=db.execute('SELECT payload FROM records WHERE role_id=? AND date=?',(key,date)).fetchone()
                derived=db.execute('SELECT payload FROM mail_derived WHERE role_id=? AND date=?',(key,date)).fetchone()
                if (before and (not derived or before[0]!=derived[0])) or (derived and not before):
                    warnings.append(prefix+'已有手动修改或撤销，保留原蓝票记录');continue
                nums=[sum(i[1] for i in mail['items'] if i[0]==490001) for mail in items]
                after=validate({'role_id':key,'date':date,'mode':'daily','first':nums[0],'second':nums[1] if len(nums)>1 else None,'note':'道馆邮件同步：邮件发送日为战斗日，按邮件时间排序。'})
                after.pop('remove');payload=json.dumps(after,ensure_ascii=False)
                if before and before[0]==payload:continue
                db.execute('INSERT INTO subjects VALUES(?,?,?,1) ON CONFLICT(role_id) DO UPDATE SET label=excluded.label,server=excluded.server',(key,group['label'],group['server']))
                db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(key,date,payload))
                db.execute('INSERT INTO mail_derived VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(key,date,payload))
                db.execute('INSERT INTO history(role_id,date,before_json,after_json,changed_at) VALUES(?,?,?,?,?)',(key,date,before[0] if before else 'null',payload,dt.datetime.now().isoformat(timespec='seconds')))
                synced+=1
        return synced,warnings,redirected

    def sync_mail_blue(self, revision, roles):
        with self.lock:
            db=self._connect()
            try:
                db.execute('BEGIN IMMEDIATE')
                if revision is not None:self._revision(db,revision)
                self._ensure_mail_archives(db,roles)
                synced,warnings,redirected=self._project_mail_blue(db,roles)
                if synced or redirected:db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
                result={'synced':synced,'warnings':warnings,'snapshot':self._load(db,roles)}
                db.commit();return result
            except Exception:db.rollback();raise
            finally:db.close()

    def _load(self, db, roles):
        if not db.in_transaction:
            db.execute('BEGIN')
        current = self._blue_roles(db,roles)
        subjects = {r['role_id']: dict(r) for r in db.execute('SELECT * FROM subjects')}
        with_records = {r[0] for r in db.execute('SELECT DISTINCT role_id FROM records')}
        hidden={r[0] for r in db.execute('SELECT source_id FROM blue_role_redirects')}
        result = []
        for key in dict.fromkeys([*current, *subjects]):
            if key in hidden:continue
            old = subjects.get(key, {})
            role = current.get(key, {'id': key, 'label': old.get('label', '历史角色'), 'server': old.get('server', ''), 'active': False})
            result.append({**role, 'selected': bool(old.get('selected')) and key in current, 'has_records': key in with_records})
        return {'revision': db.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0], 'roles': result,
                'records': [json.loads(row['payload']) for row in db.execute('SELECT role_id,payload FROM records ORDER BY date,role_id') if row['role_id'] not in hidden]}

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
        with self.lock:
            db = self._connect()
            try:
                db.execute('BEGIN IMMEDIATE'); self._revision(db, revision)
                current=self._blue_roles(db,roles)
                if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(key not in current for key in ids):raise ValueError('参与角色列表无效，请刷新后选择')
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
        with self.lock:
            db = self._connect()
            try:
                db.execute('BEGIN IMMEDIATE'); self._revision(db, revision)
                current=self._blue_roles(db,roles)
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


    @staticmethod
    def _archive_id(scope):
        return 'resource-'+hashlib.sha256(scope.encode('utf-8')).hexdigest()[:24]

    def _ensure_mail_archives(self, db, roles):
        labels=self._roles(roles)
        for row in db.execute(f"SELECT scope,role_id FROM mail_rewards WHERE {MAIL_REWARD_FILTER} GROUP BY scope").fetchall():
            old=db.execute('SELECT archive_id FROM mail_archives WHERE scope=?',(row['scope'],)).fetchone()
            if old:continue
            role=labels.get(row['role_id'],{})
            if not role:
                stored=db.execute('SELECT label,server FROM subjects WHERE role_id=?',(row['role_id'],)).fetchone()
                role=dict(stored) if stored else {}
            key=self._archive_id(row['scope'])
            db.execute('INSERT INTO mail_archives VALUES(?,?,?,?)',(row['scope'],key,role.get('label','历史角色'),role.get('server','')))
            db.execute('UPDATE mail_rewards SET role_id=? WHERE scope=?',(key,row['scope']))

    def _mail_archive_snapshot(self, db):
        return {'revision':db.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0],
                'roles':[{'id':r['archive_id'],'label':r['label'],'server':r['server'],'selected':True,'active':True,'has_records':True}
                         for r in db.execute(f'SELECT * FROM mail_archives WHERE scope IN (SELECT scope FROM mail_rewards WHERE {MAIL_REWARD_FILTER}) ORDER BY rowid')]}

    def mail_archives(self, roles=()):
        with self.lock:
            db=self._connect()
            try:
                db.execute('BEGIN IMMEDIATE');self._ensure_mail_archives(db,roles)
                result=self._mail_archive_snapshot(db);db.commit();return result
            except Exception:db.rollback();raise
            finally:db.close()

    def mail_records(self, roles):
        with self.lock:
            db=self._connect()
            try:
                db.execute('BEGIN IMMEDIATE');self._ensure_mail_archives(db,roles);db.commit()
                labels=self._roles(roles)
                labels.update({r['archive_id']:{'label':r['label'],'server':r['server']} for r in db.execute('SELECT * FROM mail_archives')})
                names={r[0]:r[1] for r in db.execute('SELECT item_id,name FROM resource_names')}
                meta={r[0]:json.loads(r[1]) for r in db.execute('SELECT item_id,payload FROM resource_meta')}
                return [{'scope':r['scope'],'uid':r['uid'],'role_id':r['role_id'],
                         'label':labels.get(r['role_id'],{}).get('label','历史角色'),'item_names':names,'item_meta':meta,
                         **json.loads(r['payload'])} for r in db.execute(f"SELECT * FROM mail_rewards WHERE {MAIL_REWARD_FILTER} ORDER BY rowid DESC")]
            finally:db.close()

    def import_mail(self, envelope, revision, roles, project_blue=True, resolved_role_id=None, standalone=False):
        # The game identity, not the UI-selected name or local cache ID, binds a receipt.
        identity=envelope.get('role',{})
        if standalone:
            for field in ('server_id','short_id'):
                value=identity.get(field)
                if type(value) is bool or not str(value).isdigit() or int(value)<=0:raise ValueError('尚未读取到已登录角色，请进入庭院后重试')
            scope=str(int(identity['server_id']))+':'+str(int(identity['short_id']))
            label=identity.get('nickname')
            if not isinstance(label,str) or not label.strip() or len(label)>100:raise ValueError('尚未读取到角色名称，请进入庭院后重试')
            role={'id':self._archive_id(scope),'nickname':label.strip(),'server':str(identity.get('server') or '区服名称待识别')[:100]}
        else:
            matches=[r for r in roles if str(r.get('short_id'))==str(identity.get('short_id')) and str(r.get('server_id'))==str(identity.get('server_id'))]
            if resolved_role_id is not None:matches=[r for r in roles if r['id']==resolved_role_id and str(r.get('short_id'))==str(identity.get('short_id'))]
            if len(matches)!=1:raise ValueError('读取到的角色未在启动器中唯一绑定，请先确认角色身份')
            role=matches[0];scope=str(identity['server_id'])+':'+str(identity['short_id'])
        key=role['id']
        mails=envelope.get('dojo_mails')
        if not isinstance(mails,list) or len(mails)>500:raise ValueError('邮件结果格式无效')
        valid={}
        for mail in mails:
            if mail.get('type')==400175 or type(mail.get('type')) is not int or not str(mail.get('reason','')).startswith(('gym','dojo')):continue
            uid=mail.get('uid');stamp=mail.get('time');items=mail.get('items')
            if not isinstance(uid,str) or not 1<=len(uid)<=128 or type(stamp) is not int or not 1262304000<=stamp<=int(dt.datetime.now().timestamp())+300:raise ValueError('邮件ID或时间无效')
            if not isinstance(items,list) or len(items)>200:raise ValueError('邮件奖励未完整加载，请打开邮箱后重试')
            rewards=[]
            for item in items:
                if not isinstance(item,(list,tuple)) or not 2<=len(item)<=5 or type(item[0]) is not int or type(item[1]) is not int or not 0<=item[1]<=1000000000:raise ValueError('邮件奖励格式未知，未保存')
                rewards.append(list(item))
            if not any(item[1]>0 for item in rewards):continue
            date=dt.datetime.fromtimestamp(stamp,dt.timezone(dt.timedelta(hours=8))).date().isoformat()
            item={'uid':uid,'type':mail['type'],'reason':mail['reason'],'time':stamp,'date':date,'items':rewards}
            if uid in valid and valid[uid]!=item:raise ValueError('同一邮件返回不同奖励，未保存')
            valid[uid]=item
        with self.lock:
            db=self._connect()
            try:
                db.execute('BEGIN IMMEDIATE');self._revision(db,revision)
                if standalone and valid:
                    db.execute('INSERT INTO mail_archives VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET label=excluded.label,server=excluded.server',(scope,key,role['nickname'],role['server']))
                    db.execute('UPDATE mail_rewards SET role_id=? WHERE scope=?',(key,scope))
                elif not standalone and not db.execute('SELECT 1 FROM subjects WHERE role_id=? AND selected=1',(key,)).fetchone():raise ValueError('请先将此角色加入蓝票记录参与名单')
                added=0;duplicates=0;warnings=[];dates=set();changed=False
                names=envelope.get('item_names',{})
                if not isinstance(names,dict):raise ValueError('物品名称表格式无效')
                reward_ids={str(i[0]) for mail in valid.values() for i in mail['items']}
                for item_id,name in names.items():
                    if str(item_id) not in reward_ids or not isinstance(name,str) or not 1<=len(name)<=160:continue
                    old_name=db.execute('SELECT name FROM resource_names WHERE item_id=?',(str(item_id),)).fetchone()
                    if not old_name or old_name[0]!=name:
                        db.execute('INSERT INTO resource_names VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET name=excluded.name',(str(item_id),name));changed=True
                meta=envelope.get('item_meta',{})
                if not isinstance(meta,dict):raise ValueError('资源星级数据格式无效')
                for item_id,info in meta.items():
                    if str(item_id) not in reward_ids or not isinstance(info,dict):continue
                    name=info.get('name','')
                    if not isinstance(name,str) or len(name)>160:raise ValueError('资源名称格式无效')
                    star=info.get('stars')
                    if star is not None and (type(star) is not int or not 1<=star<=6):raise ValueError('结界卡星级无效')
                    kind=info.get('kind','resource')
                    if kind not in ('resource','realm_card'):raise ValueError('资源类型无效')
                    payload=json.dumps({'name':name,'kind':kind,'stars':star},ensure_ascii=False,sort_keys=True)
                    before=db.execute('SELECT payload FROM resource_meta WHERE item_id=?',(str(item_id),)).fetchone()
                    if not before or before[0]!=payload:
                        db.execute('INSERT INTO resource_meta VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET payload=excluded.payload',(str(item_id),payload));changed=True
                for uid,mail in valid.items():
                    old=db.execute('SELECT payload FROM mail_rewards WHERE scope=? AND uid=?',(scope,uid)).fetchone()
                    payload=json.dumps(mail,ensure_ascii=False,sort_keys=True)
                    if old:
                        if old[0]!=payload:warnings.append('同一邮件奖励发生变化，已保留原记录：'+uid)
                        duplicates+=1
                    else:
                        db.execute('INSERT INTO mail_rewards VALUES(?,?,?,?)',(scope,uid,key,payload));added+=1
                    dates.add(mail['date'])
                for date in (dates if project_blue and not standalone else []):
                    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM mail_rewards WHERE scope=?',(scope,))]
                    daily=sorted([m for m in rows if m['date']==date and m['type']==400179],key=lambda m:(m['time'],m['uid']))
                    if not daily:continue
                    if len(daily)>2 or any(not m['items'] for m in daily):
                        warnings.append(date+'：邮件超过两封或奖励未完整加载，全部资源已保存，蓝票视图未自动填写');continue
                    if date>dt.date.today().isoformat():continue
                    old=db.execute('SELECT payload FROM records WHERE role_id=? AND date=?',(key,date)).fetchone()
                    derived=db.execute('SELECT payload FROM mail_derived WHERE role_id=? AND date=?',(key,date)).fetchone()
                    if (old and (not derived or old[0]!=derived[0])) or (derived and not old):
                        warnings.append(date+'：已有手动记录，已保留；全部邮件资源已单独保存');continue
                    nums=[sum(i[1] for i in m['items'] if i[0]==490001) for m in daily]
                    after=validate({'role_id':key,'date':date,'mode':'daily','first':nums[0],'second':nums[1] if len(nums)>1 else None,
                        'note':'邮件读取：按邮件发送时间排序，日期按北京时间；不代表战斗发生日期。'})
                    after.pop('remove');text=json.dumps(after,ensure_ascii=False)
                    if old and old[0]==text:continue
                    changed=True
                    db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(key,date,text))
                    db.execute('INSERT INTO mail_derived VALUES(?,?,?) ON CONFLICT(role_id,date) DO UPDATE SET payload=excluded.payload',(key,date,text))
                    db.execute('INSERT INTO history(role_id,date,before_json,after_json,changed_at) VALUES(?,?,?,?,?)',(key,date,old[0] if old else 'null',text,dt.datetime.now().isoformat(timespec='seconds')))
                synced=0;redirected=False
                if standalone and project_blue:
                    synced,sync_warnings,redirected=self._project_mail_blue(db,roles,{scope});warnings.extend(sync_warnings)
                if added or changed or synced or redirected:db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
                result={'added':added,'duplicates':duplicates,'synced':synced,'warnings':warnings,'label':str(identity.get('nickname') or role.get('nickname') or role.get('name')),'loaded_count':envelope.get('loaded_count',0),'snapshot':self._mail_archive_snapshot(db) if standalone else self._load(db,roles)}
                db.commit();return result
            except Exception:db.rollback();raise
            finally:db.close()
