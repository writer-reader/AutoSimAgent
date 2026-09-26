# 提供任务与审批状态查询接口，以及任务历史列表 / 事件回放（M0 起）。
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import TaskEventsResponse, TaskListItem, TaskListResponse, TaskStatusResponse
from app.services.orchestrator_service import registry

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: str | None = Query(None, description="按状态过滤（created/running/awaiting_approval/completed/failed）"),
    paper_id: str | None = Query(None, description="按论文过滤"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> TaskListResponse:
    """列出任务（按创建时间倒序）。M0 起落库，重启后仍在。"""
    items_raw = registry.list_tasks(status=status, paper_id=paper_id, limit=limit, offset=offset)
    items = [TaskListItem(**{k: t.get(k) for k in
                             ("task_id", "paper_id", "status", "stage", "error", "created_at", "updated_at")
                             if t.get(k) is not None}) for t in items_raw]
    # 没有 total 接口时用 len 近似（单用户场景 limit 足够）
    return TaskListResponse(items=items, total=len(items), offset=offset, limit=limit)


@router.get("/{task_id}", response_model=TaskStatusResponse)
# get_task 函数，查询任务状态。
def get_task(task_id: str) -> TaskStatusResponse:
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return TaskStatusResponse(**{k: task[k] for k in ("task_id", "status", "stage", "error", "result", "criteria")})


@router.get("/{task_id}/events", response_model=TaskEventsResponse)
def task_events(task_id: str, after_seq: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000)) -> TaskEventsResponse:
    """任务历史事件回放（调试 / 评测 / 断线补传）。

    返回 seq > after_seq 的事件（最多 limit 条），{seq, type, data}。
    """
    if registry.get(task_id) is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    events = registry.read_events(task_id, after_seq, limit)
    return TaskEventsResponse(task_id=task_id, after_seq=after_seq, events=events)
