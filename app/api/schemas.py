# 定义 API 请求和响应模型。
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# PaperImportRequest 类，封装该模块中的相关状态与行为。
class PaperImportRequest(BaseModel):
    local_path: str
    metadata: dict[str, str] = Field(default_factory=dict)


# PaperImportResponse 类，封装该模块中的相关状态与行为。
class PaperImportResponse(BaseModel):
    paper_id: str
    pdf_path: str
    file_hash: str


# TaskStatusResponse 类，封装该模块中的相关状态与行为。
class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    stage: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    criteria: list[dict[str, Any]] | None = None  # 验收标准（已完成任务恢复展示用）


# TaskListItem 类，任务列表项（不含 result，轻量）。
class TaskListItem(BaseModel):
    task_id: str
    paper_id: str
    status: str
    stage: str | None = None
    error: str | None = None
    created_at: float
    updated_at: float


# TaskListResponse 类，任务列表响应。
class TaskListResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    offset: int
    limit: int


# TaskEventsResponse 类，任务历史事件回放。
class TaskEventsResponse(BaseModel):
    task_id: str
    after_seq: int
    events: list[dict[str, Any]]


# WorkflowStartRequest 类，封装该模块中的相关状态与行为。
class WorkflowStartRequest(BaseModel):
    paper_id: str
    pdf_path: str
    user_id: str = "local"
