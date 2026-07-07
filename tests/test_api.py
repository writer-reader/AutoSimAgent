# 测试 API 层：健康检查、论文导入、任务查询 404、workflow 启动登记。
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "test-model")
    monkeypatch.setenv("MINERU_API_KEY", "test-mineru")
    from app.api.dependencies import get_config
    get_config.cache_clear()  # 避免跨用例缓存
    from app.api.main import create_app
    return TestClient(create_app())


# test_health 测试健康检查端点。
def test_health(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/health").json() == {"status": "ok"}


# test_task_not_found 测试查询不存在任务返回 404。
def test_task_not_found(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/tasks/task_missing").status_code == 404


# test_paper_import 测试论文导入端点。
def test_paper_import(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    client = _client(monkeypatch)
    resp = client.post("/papers/import", json={"local_path": str(pdf), "metadata": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper_id"].startswith("paper_")


# test_workflow_start_registers_task 测试启动 workflow 登记任务（背景任务不真跑）。
def test_workflow_start_registers_task(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch)
    # 用假 orchestrator 覆盖，避免真实后台流水执行
    import app.api.routers.workflow as wf_router

    class _NoopOrch:
        def run_pipeline(self, *a, **k):
            pass

    from app.api.dependencies import get_orchestrator
    client.app.dependency_overrides[get_orchestrator] = lambda: _NoopOrch()
    resp = client.post("/workflow/start", json={"paper_id": "paper_x", "pdf_path": "x.pdf"})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    assert task_id.startswith("task_")
    # 状态可查
    assert client.get(f"/workflow/{task_id}").status_code == 200
