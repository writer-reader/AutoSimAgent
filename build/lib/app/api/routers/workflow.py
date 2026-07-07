# 提供工作流启动（异步）、状态查询与审批 resume 接口。
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import get_orchestrator
from app.api.schemas import TaskStatusResponse, WorkflowStartRequest
from app.services.orchestrator_service import OrchestratorService, registry

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/start", response_model=TaskStatusResponse)
# start_workflow 函数，异步启动完整流水（图外预处理 + 图内决策）。
def start_workflow(
    request: WorkflowStartRequest,
    background: BackgroundTasks,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> TaskStatusResponse:
    task_id = registry.create(request.paper_id, request.user_id)
    background.add_task(orchestrator.run_pipeline, task_id, request.paper_id, request.pdf_path, request.user_id)
    return TaskStatusResponse(task_id=task_id, status="created", stage="pending")


@router.get("/{task_id}", response_model=TaskStatusResponse)
# get_workflow 函数，查询任务状态。
def get_workflow(task_id: str) -> TaskStatusResponse:
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return TaskStatusResponse(**{k: task[k] for k in ("task_id", "status", "stage", "error", "result")})


@router.post("/{task_id}/resume", response_model=TaskStatusResponse)
# resume_workflow 函数，审批后恢复执行（真中断 resume 占位，返回当前状态）。
def resume_workflow(task_id: str, approved: bool = True) -> TaskStatusResponse:
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    # 真 interrupt() resume 逻辑待接：当前审批为自动通过，故直接回状态。
    return TaskStatusResponse(**{k: task[k] for k in ("task_id", "status", "stage", "error", "result")})
