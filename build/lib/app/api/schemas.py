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


# WorkflowStartRequest 类，封装该模块中的相关状态与行为。
class WorkflowStartRequest(BaseModel):
    paper_id: str
    pdf_path: str
    user_id: str = "local"
