# 提供任务与审批状态查询接口。
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import TaskStatusResponse
from app.services.orchestrator_service import registry

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
# get_task 函数，查询任务状态。
def get_task(task_id: str) -> TaskStatusResponse:
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return TaskStatusResponse(**{k: task[k] for k in ("task_id", "status", "stage", "error", "result")})
