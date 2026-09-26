# 任务列表 / 事件回放端点测试（M0：会话留存 + 透明化事件）。
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "test-model")
    monkeypatch.setenv("MINERU_API_KEY", "test-mineru")
    from app.api.dependencies import get_config
    get_config.cache_clear()
    from app.api.main import create_app
    return TestClient(create_app())


def test_list_events_replay_endpoints(monkeypatch):
    client = _client(monkeypatch)
    from app.services.orchestrator_service import registry

    tid = registry.create("paper_demo", "local")
    registry.push_event(tid, {"type": "stage", "stage": "mineru", "label": "PDF 解析中"})
    registry.push_event(tid, {"type": "knowledge_done", "criteria_count": 2,
                              "knowledge": {"equations": [{"latex": "x=1"}], "parameters": []}})
    registry.update(tid, status="completed", stage="done", result={"tool_calls": 1})

    # GET /tasks 列表
    r = client.get("/tasks")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["task_id"] == tid for i in items)
    assert next(i for i in items if i["task_id"] == tid)["status"] == "completed"

    # GET /tasks/{id} 状态查询带 result
    r2 = client.get(f"/tasks/{tid}")
    assert r2.status_code == 200 and r2.json()["result"]["tool_calls"] == 1

    # GET /tasks/{id}/events 回放（含透明化 knowledge 字段）
    r3 = client.get(f"/tasks/{tid}/events")
    assert r3.status_code == 200
    evs = r3.json()["events"]
    assert len(evs) == 2
    # 事件 data 里应带 type 与 knowledge 摘要
    kd = evs[1]["data"]
    assert kd["type"] == "knowledge_done" and kd["knowledge"]["equations"][0]["latex"] == "x=1"

    # 增量回放：after_seq 只取后半段
    first_seq = evs[0]["seq"]
    r4 = client.get(f"/tasks/{tid}/events?after_seq={first_seq}")
    assert len(r4.json()["events"]) == 1


def test_tasks_404(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/tasks/nope").status_code == 404
    assert client.get("/tasks/nope/events").status_code == 404
    assert client.get("/tasks").status_code == 200  # 空列表也 200
