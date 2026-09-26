# 断点恢复 + 文件上传 测试。
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.graph.nodes import NodeDeps
from app.graph.state import WorkflowState
from app.graph.workflow import ControlWorkflow


def _client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "test-model")
    monkeypatch.setenv("MINERU_API_KEY", "test-mineru")
    from app.api.dependencies import get_config
    get_config.cache_clear()
    from app.api.main import create_app
    return TestClient(create_app())


# ── 文件上传 ────────────────────────────────────────────────

def test_papers_upload(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    pdf_bytes = b"%PDF-1.4 test body for upload"
    r = client.post(
        "/papers/upload",
        files={"file": ("upload.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["paper_id"].startswith("paper_")
    assert body["pdf_path"].endswith(".pdf")
    assert Path(body["pdf_path"]).exists()
    assert Path(body["pdf_path"]).read_bytes() == pdf_bytes


def test_papers_upload_empty_rejected(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/papers/upload", files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")})
    assert r.status_code == 400  # 空文件被 DownloadError 拦


# ── 重启端点守卫 ────────────────────────────────────────────

def test_restart_endpoint_guards(monkeypatch):
    client = _client(monkeypatch)
    from app.api.dependencies import get_orchestrator
    from app.services.orchestrator_service import registry

    # stub orchestrator：只测端点守卫，不真跑 restart_pipeline（避免拉起 MATLAB）
    class _StubOrch:
        def restart_pipeline(self, _tid):
            pass
    client.app.dependency_overrides[get_orchestrator] = lambda: _StubOrch()

    tid = registry.create("paper_g", "local")
    # interrupted 可重启
    registry.update(tid, status="interrupted")
    r = client.post(f"/workflow/{tid}/restart")
    assert r.status_code == 200 and r.json()["status"] == "running"
    # completed 不可重启
    tid2 = registry.create("paper_g2", "local")
    registry.update(tid2, status="completed")
    assert client.post(f"/workflow/{tid2}/restart").status_code == 400
    # 不存在
    assert client.post("/workflow/nope/restart").status_code == 404


# ── 孤儿扫描：running→interrupted ───────────────────────────

def test_orphan_scan_marks_running_interrupted(monkeypatch):
    from app.services.orchestrator_service import registry
    t1 = registry.create("paper_o1", "local")
    t2 = registry.create("paper_o2", "local")
    registry.update(t1, status="running")
    registry.update(t2, status="awaiting_approval")  # 不动
    n = registry.mark_orphans_interrupted()
    assert n >= 1
    assert registry.get(t1)["status"] == "interrupted"
    assert registry.get(t2)["status"] == "awaiting_approval"  # 审批等待不受影响


# ── ControlWorkflow 断点续跑：invoke(None) 不从头重跑 ─────────

def test_resume_from_checkpoint_does_not_restart(monkeypatch, tmp_path):
    """有 checkpoint 时 resume_from_checkpoint 应从断点续跑，而非重灌输入从 START 重跑。"""
    from langgraph.checkpoint.sqlite import SqliteSaver
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "ckpt.db"), check_same_thread=False)
    cp = SqliteSaver(conn)

    calls: list[str] = []
    def planner(state):
        calls.append("plan")
        return {"objective": "X", "steps": ["s1"]}
    def codegen(state):
        calls.append("gen")
        return "x=1;"
    def executor(code, state):
        calls.append("exec")
        return True, "ok", "", []
    deps = NodeDeps(planner=planner, codegen=codegen, executor=executor)

    tid = "task_ckpt_demo"
    wf1 = ControlWorkflow(deps, checkpointer=cp, auto_approve=True)
    wf1.run(WorkflowState(trace_id=tid, task_id=tid, paper_id="p"))
    plan_calls_after_run = calls.count("plan")
    assert plan_calls_after_run >= 1

    # 新实例（模拟重启），同一 sqlite 库
    conn2 = sqlite3.connect(str(tmp_path / "ckpt.db"), check_same_thread=False)
    cp2 = SqliteSaver(conn2)
    wf2 = ControlWorkflow(deps, checkpointer=cp2, auto_approve=True)
    assert wf2.has_checkpoint(tid) is True
    wf2.resume_from_checkpoint(tid)
    # 续跑不应再次调用 plan（已到 END，invoke(None) 直接返回终态）
    assert calls.count("plan") == plan_calls_after_run, "resume_from_checkpoint 不应从头重跑"
    conn.close(); conn2.close()
