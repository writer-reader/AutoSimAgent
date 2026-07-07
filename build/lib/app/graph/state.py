# 定义 LangGraph 工作流共享状态结构（去 RAG，加分层错误回滚与工具调用留痕）。
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 错误层级：L1 瞬时 / L2 代码级 / L3 方案级 / L4 知识级 / L5 致命。
ErrorLayer = Literal["L1", "L2", "L3", "L4", "L5"]


# Artifact 类，工具产出物（图/数据/模型/代码），只存路径不存内容。
class Artifact(BaseModel):
    kind: Literal["figure", "data", "model", "code"]
    path: str
    label: str = ""


# ToolCallRecord 类，单次工具调用的完整留痕记录（append-only）。
class ToolCallRecord(BaseModel):
    index: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = False
    stdout: str = ""
    stderr: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)
    error_layer: ErrorLayer | None = None
    ts: float | None = None


# WorkflowError 类，工作流中的一次错误记录，携带层级供路由决策。
class WorkflowErrorRecord(BaseModel):
    layer: ErrorLayer
    code: str = ""
    message: str = ""
    tool_index: int | None = None


# RetryBudget 类，各层独立的重试计数。
class RetryBudget(BaseModel):
    l1: int = 0
    l2: int = 0
    l3: int = 0
    l4: int = 0
    calib: int = 0   # 结果校准迭代计数（跑通但指标不达标）


# WorkflowState 类，工作流全量共享状态（Pydantic）。
class WorkflowState(BaseModel):
    trace_id: str
    task_id: str
    paper_id: str
    user_id: str = "local"

    # 图外预处理产出的引用
    parsed_doc_ref: str = ""          # ParsedPaper 落盘路径
    knowledge_json: str = ""          # MergedKnowledge 落盘路径

    # 图内决策产物
    plan: dict[str, Any] = Field(default_factory=dict)          # 规划 JSON
    generated_code: str = ""                                    # 当前代码
    generated_code_paths: list[str] = Field(default_factory=list)
    generated_model_paths: list[str] = Field(default_factory=list)

    # 结果校准
    acceptance_criteria: list[dict[str, Any]] = Field(default_factory=list)  # 论文验收标准
    computed_metrics: dict[str, Any] = Field(default_factory=dict)           # 代码算出的指标(results.json)
    verdict: dict[str, Any] = Field(default_factory=dict)                    # 逐条比对判定

    # 工具调用留痕（append-only 列表）
    tool_results: list[ToolCallRecord] = Field(default_factory=list)
    tool_call_seq: int = 0            # 全局调用序号

    # 审批
    approval_request: dict[str, Any] | None = None
    approval_status: Literal["pending", "approved", "rejected", "none"] = "none"

    # 校验与错误
    verification_result: dict[str, Any] = Field(default_factory=dict)
    errors: list[WorkflowErrorRecord] = Field(default_factory=list)
    retries: RetryBudget = Field(default_factory=RetryBudget)

    status: Literal["running", "completed", "failed"] = "running"

    # next_index 方法，取下一个工具调用序号并自增。
    def next_index(self) -> int:
        idx = self.tool_call_seq
        self.tool_call_seq += 1
        return idx

    # latest_error 方法，取最近一次错误记录。
    def latest_error(self) -> WorkflowErrorRecord | None:
        return self.errors[-1] if self.errors else None

    # latest_tool 方法，取最近一次工具调用记录。
    def latest_tool(self) -> ToolCallRecord | None:
        return self.tool_results[-1] if self.tool_results else None
