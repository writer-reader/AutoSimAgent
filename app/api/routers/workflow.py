# 工作流 API 路由：启动、状态查询、SSE 实时流、人工审批 resume。
from __future__ import annotations

import asyncio
import json
import queue as stdlib_queue
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.api.dependencies import get_orchestrator
from app.api.schemas import TaskStatusResponse, WorkflowStartRequest
from app.services.orchestrator_service import OrchestratorService, registry

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/start", response_model=TaskStatusResponse)
def start_workflow(
    request: WorkflowStartRequest,
    background: BackgroundTasks,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> TaskStatusResponse:
    """异步启动完整流水（图外预处理 + 图内决策）。"""
    task_id = registry.create(request.paper_id, request.user_id)
    background.add_task(orchestrator.run_pipeline, task_id, request.paper_id, request.pdf_path, request.user_id)
    return TaskStatusResponse(task_id=task_id, status="created", stage="pending")


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_workflow(task_id: str) -> TaskStatusResponse:
    """查询任务状态（轮询用；实时监控推荐用 /stream）。"""
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return TaskStatusResponse(**{k: task[k] for k in ("task_id", "status", "stage", "error", "result")})


@router.get("/{task_id}/stream")
async def stream_workflow(task_id: str):
    """SSE 实时事件流。

    客户端接收 text/event-stream；每行格式：
      data: <JSON>\\n\\n

    事件 type 值：
      stage       — 阶段切换（label 字段描述当前在做什么）
      node        — LangGraph 节点 start/done
      knowledge_done — 知识抽取完成（criteria_count 字段）
      interrupt   — 图在审批点暂停，payload 含代码预览（需调用 POST /resume）
      resume      — 人工决定已传入，图继续
      done        — 全流程结束（status / result 字段）
      error       — 异常
      heartbeat   — 心跳（每 15s 发一次，防连接超时）
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    q = registry.get_queue(task_id)
    if q is None:
        raise HTTPException(status_code=404, detail="event_queue_not_found")

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 非阻塞地从线程安全队列取事件（最多等 15s，超时发心跳）
                event = await loop.run_in_executor(None, _queue_get_with_timeout, q, 15.0)
                if event is None:
                    # 哨兵：流正常结束
                    yield f"data: {json.dumps({'type': 'done', 'reason': 'sentinel'})}\n\n"
                    return
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                # 终态事件后关闭流
                if event.get("type") in ("done", "error"):
                    return
            except _QueueTimeout:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{task_id}/resume", response_model=TaskStatusResponse)
def resume_workflow(
    task_id: str,
    approved: bool = True,
    edited_code: str | None = None,
    interrupt_key: str | None = None,
    background: BackgroundTasks = None,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> TaskStatusResponse:
    """人工审批后恢复图执行。

    - approved=true   → 执行生成的 MATLAB 代码（可同时传 edited_code 覆盖代码）
    - approved=false  → 拒绝，图回退到 plan 节点重新规划
    - edited_code     → （可选）替换 LLM 生成的代码后再执行
    - interrupt_key   → 本次审批的唯一标识，由 SSE interrupt 事件携带，用于多轮审批定位
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.get("status") != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"task not awaiting approval (status={task.get('status')})")

    background.add_task(orchestrator.resume_pipeline, task_id, approved, edited_code, interrupt_key)
    return TaskStatusResponse(task_id=task_id, status="running", stage="resuming")


@router.get("/{task_id}/code/{filename}", response_class=PlainTextResponse)
def get_code_file(task_id: str, filename: str) -> str:
    """返回任务生成的代码文件内容（供前端 Monaco 只读预览和下载）。

    从任务的 result.code_paths 中查找与 filename 匹配的文件路径并返回其内容。
    只允许读取以 .m 或 .slx 结尾的文件，防止目录穿越。
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    result = task.get("result") or {}
    code_paths: list[str] = result.get("code_paths", [])

    # 防御：只允许安全的文件名（无路径分隔符、无 ..）
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid_filename")

    # 从 code_paths 中找到与 filename 匹配的路径
    matched: str | None = None
    for p in code_paths:
        if Path(p).name == filename:
            matched = p
            break

    if matched is None:
        raise HTTPException(status_code=404, detail="code_file_not_found")

    file_path = Path(matched)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="code_file_missing_on_disk")

    return file_path.read_text(encoding="utf-8")


# ── 队列工具 ────────────────────────────────────────────────────────────────

class _QueueTimeout(Exception):
    pass


def _queue_get_with_timeout(q: stdlib_queue.Queue, timeout: float):
    """带超时的同步队列 get，超时抛 _QueueTimeout（供 run_in_executor 调用）。"""
    try:
        return q.get(timeout=timeout)
    except stdlib_queue.Empty:
        raise _QueueTimeout()
