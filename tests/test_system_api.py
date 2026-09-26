# /system/status 实时监测端点测试。
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "test-model")
    monkeypatch.setenv("MINERU_API_KEY", "test-mineru")
    from app.api.dependencies import get_config
    get_config.cache_clear()
    from app.api.main import create_app
    return TestClient(create_app())


def test_system_status_shape(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["pid"] > 0 and body["uptime_s"] >= 0
    assert set(body["tasks"]) == {"total", "by_status", "active"}
    assert body["events_total"] == 0  # 隔离测试库为空
    assert body["db"]["path"].endswith(".db")
    # MATLAB MCP 未初始化（测试进程从未启动过它）
    assert body["matlab_mcp"]["initialized"] is False
    # LLM 摘要不含密钥，只报 host 与模型名
    assert body["llm"]["configured"] is True
    assert body["llm"]["base_url_host"] == "api.example.com"
    assert body["llm"]["default_model"] == "test-model"
    assert "key" not in str(body).lower() or "test-key" not in str(body)


def test_system_status_reflects_tasks(monkeypatch):
    client = _client(monkeypatch)
    from app.services.orchestrator_service import registry
    tid = registry.create("paper_m", "local")
    registry.update(tid, status="running", stage="graph:plan")
    r = client.get("/system/status")
    body = r.json()
    assert body["tasks"]["by_status"].get("running") == 1
    assert any(a["task_id"] == tid for a in body["tasks"]["active"])
