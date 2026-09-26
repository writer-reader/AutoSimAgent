# 工作流 API 路由：启动、状态查询、SSE 实时流（从事件库增量读，支持 Last-Event-ID 续传）、人工审批 resume。
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from app.api.dependencies import get_orchestrator
from app.api.schemas import TaskStatusResponse, WorkflowStartRequest
from app.services.orchestrator_service import OrchestratorService, registry

router = APIRouter(prefix="/workflow", tags=["workflow"])

# SSE 轮询间隔（秒）：无新事件时多久再查一次事件库。
_POLL_INTERVAL = 0.4
# 心跳间隔（秒）：长时间无事件时发心跳防连接超时。
_HEARTBEAT_INTERVAL = 15.0


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
async def stream_workflow(task_id: str, request: Request):
    """SSE 实时事件流（从事件库增量读取，重启不丢、断线可续传）。

    客户端接收 text/event-stream；每条事件格式：
      id: <seq>\\n
      data: <JSON>\\n\\n

    - `id` 为全局递增 seq，客户端断线重连时 EventSource 自动带 Last-Event-ID 头续传。
    - 事件 type：stage / node / knowledge_done / interrupt / resume / done / error / heartbeat。
    - node 事件携带透明化详情（M0 起）：plan JSON、生成代码、工具 stdout/stderr 尾部与指标、验收逐条判定。
    - 终态（done/error 事件 或 任务 status∈{completed,failed}）后流自动收尾。
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    # Last-Event-ID 头优先，其次 query 参数 after_seq
    last_id = request.headers.get("last-event-id") or request.query_params.get("after_seq") or "0"
    try:
        after_seq = max(0, int(str(last_id)))
    except ValueError:
        after_seq = 0

    loop = asyncio.get_event_loop()

    async def event_generator():
        nonlocal after_seq
        heartbeat_at = time.monotonic() + _HEARTBEAT_INTERVAL
        while True:
            events = await loop.run_in_executor(None, registry.read_events, task_id, after_seq, 200)
            if events:
                for ev in events:
                    after_seq = ev["seq"]
                    yield f"id: {ev['seq']}\ndata: {json.dumps(ev['data'], ensure_ascii=False)}\n\n"
                    if ev["data"].get("type") in ("done", "error"):
                        return
                heartbeat_at = time.monotonic() + _HEARTBEAT_INTERVAL
                continue
            # 无新事件：任务已到终态则收尾，否则心跳保活
            if registry.is_terminal(task_id):
                yield f"data: {json.dumps({'type': 'done', 'reason': 'sentinel'})}\n\n"
                return
            if time.monotonic() >= heartbeat_at:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                heartbeat_at = time.monotonic() + _HEARTBEAT_INTERVAL
            await asyncio.sleep(_POLL_INTERVAL)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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

    重启后也能 resume：workflow 实例不在内存时，orchestrator 凭 checkpointer 重建（thread_id=task_id 续上状态）。
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.get("status") != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"task not awaiting approval (status={task.get('status')})")

    background.add_task(orchestrator.resume_pipeline, task_id, approved, edited_code, interrupt_key)
    return TaskStatusResponse(task_id=task_id, status="running", stage="resuming")


@router.post("/{task_id}/restart", response_model=TaskStatusResponse)
def restart_workflow(
    task_id: str,
    background: BackgroundTasks,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> TaskStatusResponse:
    """崩溃恢复：从最近 checkpoint 续跑（进程被杀/重启后半截任务恢复，或失败后重试）。

    适用 status=interrupted（启动扫描把被杀的 running 标记而来）/ running / failed。
    有 checkpoint → invoke(None, config) 从最后完成节点续跑（连回滚中断点都能续）；
    无 checkpoint（死在图外预处理）→ 幂等重跑图外预处理（MinerU/adapter/知识均复用缓存）再进图。
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.get("status") not in ("interrupted", "running", "failed"):
        raise HTTPException(status_code=400, detail=f"task not restartable (status={task.get('status')})")

    background.add_task(orchestrator.restart_pipeline, task_id)
    return TaskStatusResponse(task_id=task_id, status="running", stage="restarting")


@router.get("/{task_id}/artifacts/{filename}")
def get_artifact_file(task_id: str, filename: str):
    """返回任务产物文件（仿真图像 .png/.jpg 等），供前端最终结果页展示。

    只允许 result.artifacts 中登记过的文件名（无路径分隔符、无 ..），防止目录穿越。
    """
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid_filename")

    artifacts: list[dict] = (task.get("result") or {}).get("artifacts", [])
    matched: str | None = None
    for a in artifacts:
        if Path(a.get("path", "")).name == filename:
            matched = a.get("path")
            break
    if matched is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")

    file_path = Path(matched)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="artifact_file_missing")
    return FileResponse(file_path)


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
