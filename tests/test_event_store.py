# 事件溯源存储测试：任务登记、事件 append-only、seq 续传、终态。
from __future__ import annotations

from app.events.store import EventStore


def test_create_update_get(tmp_path):
    store = EventStore(tmp_path / "a.db")
    assert store.create_task("t1", "paper_a", "local")
    assert not store.create_task("t1", "paper_a", "local")  # 重复登记忽略
    t = store.get_task("t1")
    assert t and t["status"] == "created" and t["paper_id"] == "paper_a"
    store.update_task("t1", status="running", stage="plan", result={"x": 1})
    t = store.get_task("t1")
    assert t["status"] == "running" and t["result"] == {"x": 1}
    store.close()


def test_events_seq_and_replay(tmp_path):
    store = EventStore(tmp_path / "b.db")
    store.create_task("t2", "p")
    s1 = store.append_event("t2", {"type": "stage", "stage": "mineru"})
    s2 = store.append_event("t2", {"type": "node", "node": "plan", "plan": {"objective": "X"}})
    assert s2 > s1 > 0
    # 全量读
    evs = store.read_events("t2", 0)
    assert [e["seq"] for e in evs] == [s1, s2]
    assert evs[1]["data"]["plan"]["objective"] == "X"
    # 增量续传：只取 s1 之后
    evs2 = store.read_events("t2", s1)
    assert len(evs2) == 1 and evs2[0]["seq"] == s2
    store.close()


def test_list_tasks_ordered(tmp_path):
    store = EventStore(tmp_path / "c.db")
    store.create_task("t3", "paper_x")
    store.create_task("t4", "paper_y")
    store.update_task("t4", status="completed")
    rows = store.list_tasks()
    assert [r["task_id"] for r in rows] == ["t4", "t3"]  # 倒序
    only_done = store.list_tasks(status="completed")
    assert [r["task_id"] for r in only_done] == ["t4"]
    store.close()


def test_persistence_across_reopen(tmp_path):
    db = tmp_path / "d.db"
    s = EventStore(db)
    s.create_task("t5", "p")
    s.append_event("t5", {"type": "stage", "stage": "mineru"})
    s.close()
    # 模拟重启：重新打开同一文件
    s2 = EventStore(db)
    assert s2.get_task("t5") is not None
    assert len(s2.read_events("t5")) == 1
    s2.close()
