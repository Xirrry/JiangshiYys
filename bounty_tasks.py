"""Daily bounty persistence and PID-bound one-shot acquisition for the launcher."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import sqlite3
import sys
import threading
from contextlib import contextmanager

import bounty_transport
import role_reader
import window_layout

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
DLL = ROOT / "hardware/bounty-reader/bounty_agent.dll"
with (ROOT / "servers.json").open(encoding="utf-8") as stream:
    SERVERS = {str(item["id"]): item["name"] for item in json.load(stream)["servers"]}


def number(value):
    return value if type(value) is int and value >= 0 else None


def normalize(document):
    role = document.get("role", {})
    server = str(role.get("server_id", ""))
    short = str(role.get("short_id", ""))
    if not server.isdigit() or not short.isdigit() or int(short) <= 0:
        raise ValueError("尚未读到有效角色身份，请先进入庭院")
    if not document.get("available") or not isinstance(document.get("tasks"), list):
        raise ValueError("悬赏数据尚未加载，请打开悬赏面板后再试")
    rows = []
    for task in document["tasks"]:
        if not isinstance(task, dict) or not isinstance(task.get("uid"), str) or not task["uid"]:
            raise ValueError("任务标识无效，本次结果未保存")
        kind = task.get("kind")
        label = "协作" if kind in (3, 7, 9) else "分享" if kind in (4, 5) else "食材" if kind == 6 else "普通" if kind in (1, 11, 12) else "其他"
        row = dict(task)
        row.update(category=label, current=number(task.get("current")), target=number(task.get("target")))
        for field in ("finished", "claimed"):
            row[field] = task.get(field) if type(task.get(field)) is bool else None
        row["name"] = task.get("name") or "名称未加载"
        row["participants"] = [
            {"label": part.get("label"), "index": part.get("index"),
             "current": number(part.get("current")), "target": number(part.get("target")), "monster": part.get("monster")}
            for part in task.get("participants", [])
        ]
        rows.append(row)
    return {"key": server + ":" + short, "name": role.get("name") or "未命名角色",
            "server": SERVERS.get(server, "未知区服")}, rows


def round_bucket(moment):
    moment = moment.replace(tzinfo=TZ) if moment.tzinfo is None else moment.astimezone(TZ)
    if moment.hour < 5:
        return (moment.date() - timedelta(days=1)).isoformat(), "evening"
    return moment.date().isoformat(), "morning" if moment.hour < 18 else "evening"


class BountyStore:
    def __init__(self, data_root, app):
        self.database = Path(data_root) / "data/daily-bounty.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.app = app
        self.read_lock = threading.Lock()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS tasks_v2 (day TEXT NOT NULL, round TEXT NOT NULL, role_key TEXT NOT NULL, uid TEXT NOT NULL, role TEXT NOT NULL, payload TEXT NOT NULL, captured_at TEXT NOT NULL, PRIMARY KEY(day,round,role_key,uid))")
            db.execute("CREATE TABLE IF NOT EXISTS bounty_meta (key TEXT PRIMARY KEY, value TEXT)")
            migrated = db.execute("SELECT value FROM bounty_meta WHERE key='rounds_v1'").fetchone()
            if not migrated:
                old = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
                if old:
                    for role_key, uid, role, payload, captured in db.execute("SELECT role_key,uid,role,payload,captured_at FROM tasks ORDER BY captured_at").fetchall():
                        day, round_name = round_bucket(datetime.fromisoformat(captured))
                        db.execute("INSERT OR REPLACE INTO tasks_v2 VALUES(?,?,?,?,?,?,?)", (day, round_name, role_key, uid, role, payload, captured))
                db.execute("INSERT INTO bounty_meta VALUES('rounds_v1','1')")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.database), timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def windows(self):
        try:
            rows = window_layout.running_game_windows(role_reader.game_pids(), self.app.process_stamp)
            return {"ok": True, "windows": [
                {"id": row["id"], "title": row["title"] or "阴阳师窗口"} for row in rows
            ]}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def history(self, day=None):
        try:
            day = day or round_bucket(datetime.now(TZ))[0]
            datetime.strptime(day, "%Y-%m-%d")
            with self.connect() as db:
                rows = db.execute("SELECT role_key,role,payload,captured_at,round FROM tasks_v2 WHERE day=? ORDER BY role_key,CASE round WHEN 'morning' THEN 0 ELSE 1 END,captured_at,uid", (day,)).fetchall()
            roles = {}
            for key, role, payload, captured, round_name in rows:
                group = roles.setdefault(key, {**json.loads(role), "tasks": [], "captured_at": captured})
                task = json.loads(payload)
                task["round"] = round_name
                task["captured_at"] = captured
                group["tasks"].append(task)
                if captured > group["captured_at"]:
                    group["captured_at"] = captured
            return {"ok": True, "day": day, "roles": list(roles.values())}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def save(self, document, observed_at=None):
        role, tasks = normalize(document)
        if not tasks:
            return role, 0
        moment = observed_at or datetime.now(TZ)
        day, round_name = round_bucket(moment)
        now = moment.astimezone(TZ).isoformat(timespec="seconds")
        with self.connect() as db:
            for task in tasks:
                db.execute("INSERT INTO tasks_v2 VALUES(?,?,?,?,?,?,?) ON CONFLICT(day,round,role_key,uid) DO UPDATE SET role=excluded.role,payload=excluded.payload,captured_at=excluded.captured_at",
                           (day, round_name, role["key"], task["uid"], json.dumps(role, ensure_ascii=False),
                            json.dumps(task, ensure_ascii=False), now))
        return role, len(tasks)

    def read(self, target="all"):
        if not self.read_lock.acquire(blocking=False):
            return {"ok": False, "error": "已有读取任务，请等待完成"}
        try:
            rows = window_layout.running_game_windows(role_reader.game_pids(), self.app.process_stamp)
            if target != "all":
                rows = [row for row in rows if row["id"] == target]
            if not rows:
                raise ValueError("未找到目标游戏窗口，请刷新列表")
            results = []
            for row in rows:
                try:
                    observed_at = datetime.now(TZ)
                    document = bounty_transport.read(
                        row["pid"], int(row["stamp"]), self.app.process_stamp, DLL, 32)
                    role, count = self.save(document, observed_at)
                    results.append({"ok": True, "title": row["title"], "role": role["name"], "count": count})
                except Exception as error:
                    results.append({"ok": False, "title": row["title"], "error": str(error)})
            return {"ok": True, "results": results, "history": self.history()}
        except Exception as error:
            return {"ok": False, "error": str(error)}
        finally:
            self.read_lock.release()
