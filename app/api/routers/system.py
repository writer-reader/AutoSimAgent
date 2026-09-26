# 系统运行状态监测端点：进程信息、任务统计、MATLAB MCP 连接态、LLM 配置、事件库大小。
# 全部只读、无副作用（绝不借此启动 MATLAB 或触发 LLM 调用）；前端每 5s 轮询一次。
from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter

from app.services.orchestrator_service import registry
from app.tools.mcp_factory import matlab_client_status

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()
_APP_VERSION = "0.1.0"

# 活跃状态：徽标上要显示"运行中 N"的那些。
_ACTIVE_STATUSES = ("created", "running", "awaiting_approval")


@router.get("/status")
def system_status() -> dict:
    """后端运行状态快照（实时监测轮询用）。

    返回：进程信息（pid/uptime/python）、任务统计（按状态分组 + 活跃任务列表）、
    事件库（事件总数/文件大小）、MATLAB MCP 连接态、LLM 配置摘要（不含密钥）。
    """
    store = registry.event_store()

    by_status = store.task_counts()
    active = [
        {"task_id": t["task_id"], "status": t["status"], "stage": t.get("stage")}
        for t in store.list_tasks(limit=50)
        if t.get("status") in _ACTIVE_STATUSES
    ][:10]

    return {
        "status": "ok",
        "app": "control-agent",
        "version": _APP_VERSION,
        "pid": os.getpid(),
        "python": platform.python_version(),
        "started_at": _STARTED_AT,
        "uptime_s": round(time.time() - _STARTED_AT, 1),
        "tasks": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "active": active,
        },
        "events_total": store.count_events(),
        "db": {"path": store.db_path, "size_bytes": store.db_size_bytes()},
        "matlab_mcp": matlab_client_status(),
        "llm": _llm_status(),
    }


# _llm_status 函数，LLM 配置摘要（尽力而为：.env 缺失时不抛错，报 configured=False）。
def _llm_status() -> dict:
    try:
        from app.api.dependencies import get_config
        cfg = get_config()
        host = urlsplit(cfg.model.base_url).hostname or ""
        return {
            "configured": True,
            "base_url_host": host,
            "default_model": cfg.model.default_llm,
            "planner_model": cfg.model.planner_llm,
        }
    except Exception:
        return {"configured": False}
