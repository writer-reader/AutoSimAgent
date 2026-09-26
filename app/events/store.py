# 事件溯源存储：tasks / events 两表落 SQLite，重启不丢。
# 设计对标 OpenHands Event Stream：事件不可变、append-only、按 seq 单调递增；
# SSE 消费者按 (task_id, seq > after_seq) 增量拉取，天然支持断线续传（Last-Event-ID）与历史回放。
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

# 任务终态：到达后 SSE 流读空即可关闭。
TERMINAL_STATUSES = ("completed", "failed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    paper_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL DEFAULT 'local',
    status      TEXT NOT NULL DEFAULT 'created',
    stage       TEXT,
    error       TEXT,
    result      TEXT,
    criteria    TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events (task_id, seq);
"""


# EventStore 类，线程安全的 SQLite 事件存储（后台线程写、SSE 线程读）。
class EventStore:
    def __init__(self, db_path: str | Path = "data/autoagent.db") -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass  # 旧 SQLite 或只读文件系统时退回默认日志模式

    # close 方法，关闭连接（进程退出时调用）。
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── 任务登记 ────────────────────────────────────────────────

    # create_task 方法，登记新任务，返回是否成功（已存在返回 False）。
    def create_task(self, task_id: str, paper_id: str, user_id: str = "local") -> bool:
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO tasks (task_id, paper_id, user_id, status, stage, created_at, updated_at) "
                "VALUES (?, ?, ?, 'created', 'pending', ?, ?)",
                (task_id, paper_id, user_id, now, now),
            )
            return cur.rowcount > 0

    # update_task 方法，更新任务元数据字段（status/stage/error/result/criteria）。
    def update_task(self, task_id: str, **kw) -> None:
        if not kw:
            return
        json_fields = {"result", "criteria"}
        sets, vals = [], []
        for k, v in kw.items():
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v, ensure_ascii=False) if k in json_fields and v is not None else v)
        sets.append("updated_at = ?")
        vals.append(time.time())
        vals.append(task_id)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?", vals)

    # get_task 方法，返回任务元数据（result/criteria 反序列化），不存在返回 None。
    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return _row_to_task(row)

    # list_tasks 方法，按创建时间倒序列出任务（可按 status/paper_id 过滤）。
    def list_tasks(
        self,
        status: str | None = None,
        paper_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conds, vals = [], []
        if status:
            conds.append("status = ?")
            vals.append(status)
        if paper_id:
            conds.append("paper_id = ?")
            vals.append(paper_id)
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        vals += [max(1, min(int(limit), 500)), max(0, int(offset))]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM tasks {where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?", vals
            ).fetchall()
        return [_row_to_task(r, with_result=False) for r in rows]

    # mark_orphans_interrupted 方法，把进程被杀留下的 status=='running' 任务标为 interrupted（可恢复）。
    # awaiting_approval 不动——它本就可经审批 resume。返回受影响行数。
    def mark_orphans_interrupted(self) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE tasks SET status='interrupted', updated_at=? WHERE status='running'",
                (time.time(),),
            )
            return cur.rowcount

    # delete_task 方法，删除任务记录及其全部事件。生成产物文件（data/code/generated/<task_id>/）
    # 不在本接口清理范围，保留在磁盘上。任务不存在返回 False。
    def delete_task(self, task_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            self._conn.execute("DELETE FROM events WHERE task_id = ?", (task_id,))
            return cur.rowcount > 0

    # ── 监测统计（/system/status 用）──────────────────────────

    # task_counts 方法，按状态分组的任务计数。
    def task_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) AS c FROM tasks GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    # count_events 方法，事件总数。
    def count_events(self) -> int:
        with self._lock:
            (n,) = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(n)

    # db_size_bytes 方法，库文件大小（监测展示用）。
    def db_size_bytes(self) -> int:
        try:
            return Path(self.db_path).stat().st_size
        except OSError:
            return 0

    # prune_events 方法，删除 keep_days 天前的事件（保留期清理，启动时调用），返回删除行数。
    # 只清 events 不动 tasks：任务元数据很小需长期保留，事件流超期后 SSE 回放随之失效，属预期。
    def prune_events(self, keep_days: int = 30) -> int:
        cutoff = time.time() - max(1, int(keep_days)) * 86400
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
            return cur.rowcount or 0

    # ── 事件日志（append-only）────────────────────────────────

    # append_event 方法，写入一条事件并返回全局 seq。
    # event 需含 type 字段；ts 缺省补当前时间。
    def append_event(self, task_id: str, event: dict) -> int:
        event = dict(event)
        event.setdefault("ts", time.time())
        etype = event.pop("type", "unknown")
        payload = json.dumps(event, ensure_ascii=False)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO events (task_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
                (task_id, etype, payload, event["ts"]),
            )
            return cur.lastrowid or 0

    # read_events 方法，读取 seq > after_seq 的事件（最多 limit 条），返回 [{seq, type, data}]。
    def read_events(self, task_id: str, after_seq: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, type, payload FROM events WHERE task_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (task_id, int(after_seq), max(1, int(limit))),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                data = json.loads(r["payload"])
            except (json.JSONDecodeError, ValueError):
                data = {}
            out.append({"seq": r["seq"], "type": r["type"], "data": {**data, "type": r["type"]}})
        return out


# _row_to_task 函数，把 DB 行转任务 dict（JSON 列反序列化）。
def _row_to_task(row: sqlite3.Row, with_result: bool = True) -> dict[str, Any]:
    task: dict[str, Any] = {
        "task_id": row["task_id"],
        "paper_id": row["paper_id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "stage": row["stage"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_result:
        task["result"] = _load_json_col(row["result"])
        task["criteria"] = _load_json_col(row["criteria"])
    return task


def _load_json_col(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
