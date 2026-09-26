# 可观测性三件套的测试：日志追踪上下文注入、访问日志中间件、事件保留期清理。
from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.access_log import AccessLogMiddleware
from app.core.logging_config import JsonFormatter
from app.core.log_context import (
    LogContextFilter,
    get_log_context,
    reset_log_context,
    set_log_context,
)
from app.events.store import EventStore


# ── 日志追踪上下文 ──────────────────────────────────────────

def test_filter_injects_fields_and_formatter_outputs_them():
    token = set_log_context(task_id="task_1", paper_id="paper_1", trace_id="task_1")
    try:
        rec = logging.LogRecord("test.mod", logging.INFO, __file__, 1, "hello", None, None)
        assert LogContextFilter().filter(rec) is True
        assert rec.task_id == "task_1"
        assert rec.paper_id == "paper_1"
        # 未设置的字段补 "-"，JsonFormatter 输出稳定
        out = json.loads(JsonFormatter().format(rec))
        assert out["task_id"] == "task_1"
        assert out["request_id"] == "-"
    finally:
        reset_log_context(token)


def test_filter_does_not_override_explicit_extra():
    token = set_log_context(task_id="from_context")
    try:
        rec = logging.LogRecord("test.mod", logging.INFO, __file__, 1, "hello", None, None)
        rec.task_id = "explicit"
        LogContextFilter().filter(rec)
        assert rec.task_id == "explicit"
    finally:
        reset_log_context(token)


def test_none_values_are_ignored_and_reset_restores_previous():
    outer = set_log_context(task_id="t_outer")
    try:
        inner = set_log_context(paper_id=None, request_id="req_1")
        try:
            assert get_log_context() == {"task_id": "t_outer", "request_id": "req_1"}
        finally:
            reset_log_context(inner)
        assert get_log_context() == {"task_id": "t_outer"}
    finally:
        reset_log_context(outer)
    assert get_log_context() == {}


# ── 访问日志中间件 ──────────────────────────────────────────

def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get("/hello")
    def hello() -> dict:
        logging.getLogger("test.endpoint").info("inside endpoint")
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("kaboom")

    return app


def _access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.api.access"]


def test_access_log_success_carries_fields_and_header(caplog):
    client = TestClient(_make_app())
    with caplog.at_level(logging.INFO, logger="app.api.access"):
        resp = client.get("/hello")
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]

    recs = _access_records(caplog)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.http_method == "GET"
    assert rec.http_path == "/hello"
    assert rec.http_status == 200
    assert rec.duration_ms >= 0
    assert rec.request_id == resp.headers["x-request-id"]
    assert rec.levelno == logging.INFO


def test_access_log_quiet_paths_are_skipped(caplog):
    app = _make_app()

    @app.get("/system/status")
    def status() -> dict:
        return {"ok": True}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="app.api.access"):
        assert client.get("/system/status").status_code == 200
    assert _access_records(caplog) == []


def test_access_log_server_error_logged_as_error(caplog):
    client = TestClient(_make_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app.api.access"):
        resp = client.get("/boom")
    assert resp.status_code == 500

    recs = _access_records(caplog)
    assert len(recs) == 1
    assert recs[0].http_status == 500
    assert recs[0].levelno == logging.ERROR


# ── 事件保留期清理 ──────────────────────────────────────────

def test_prune_events_deletes_only_old_ones(tmp_path):
    store = EventStore(tmp_path / "prune.db")
    try:
        store.create_task("t1", "paper_1")
        now = time.time()
        old_seq = store.append_event("t1", {"type": "old", "ts": now - 40 * 86400})
        new_seq = store.append_event("t1", {"type": "new", "ts": now})

        deleted = store.prune_events(keep_days=30)

        assert deleted == 1
        remaining = store.read_events("t1")
        assert [e["seq"] for e in remaining] == [new_seq]
        # 再清一次无残留
        assert store.prune_events(keep_days=30) == 0
        assert old_seq > 0
    finally:
        store.close()
