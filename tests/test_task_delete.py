# tests/test_task_delete.py — 任务删除：记录与事件一并清除，不存在返回 False。
from __future__ import annotations

from app.events.store import EventStore


# test_delete_removes_task_and_events 测试删除任务行与事件，get/list 均不再可见。
def test_delete_removes_task_and_events(tmp_path) -> None:
    store = EventStore(str(tmp_path / "t.db"))
    task_id = "task_deleteme"
    store.create_task(task_id, "paper_x")
    store.append_event(task_id, {"type": "stage", "stage": "mineru", "label": "解析"})
    store.update_task(task_id, status="failed", stage="done", error="boom")

    assert store.delete_task(task_id) is True
    assert store.get_task(task_id) is None
    assert store.list_tasks() == []
    assert store.read_events(task_id) == []


# test_delete_missing_returns_false 测试删除不存在的任务返回 False（不抛错）。
def test_delete_missing_returns_false(tmp_path) -> None:
    store = EventStore(str(tmp_path / "t.db"))
    assert store.delete_task("task_never_existed") is False
