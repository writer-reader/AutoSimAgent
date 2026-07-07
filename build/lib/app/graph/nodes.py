# 工作流节点实现。节点先以「可注入依赖」形式落地：
# 默认占位逻辑用于跑通图与分层路由单测；后续把 planner/codegen/executor 换成真实 LLM/MCP。
from __future__ import annotations

from typing import Any, Callable, Protocol

from app.graph.router import classify_error
from app.graph.state import Artifact, ToolCallRecord, WorkflowErrorRecord, WorkflowState


# Planner 协议，输入 state 产出 plan dict。
class Planner(Protocol):
    def __call__(self, state: WorkflowState) -> dict[str, Any]: ...


# CodeGen 协议，输入 state 产出 MATLAB 代码字符串。
class CodeGen(Protocol):
    def __call__(self, state: WorkflowState) -> str: ...


# Executor 协议，执行代码返回 (ok, stdout, stderr, artifacts)。
class Executor(Protocol):
    def __call__(self, code: str, state: WorkflowState) -> tuple[bool, str, str, list[Artifact]]: ...


# Verifier 协议，输入 state 产出判定 dict（passed/results/summary）。
class Verifier(Protocol):
    def __call__(self, state: WorkflowState) -> dict[str, Any]: ...


# NodeDeps 类，聚合节点的可注入依赖。
class NodeDeps:
    # __init__ 方法，注入 planner/codegen/executor/verifier（缺省用占位实现）。
    def __init__(
        self,
        planner: Planner | None = None,
        codegen: CodeGen | None = None,
        executor: Executor | None = None,
        verifier: Verifier | None = None,
        tool_name: str = "evaluate_matlab_code",
    ) -> None:
        self.planner = planner or _stub_planner
        self.codegen = codegen or _stub_codegen
        self.executor = executor or _stub_executor
        self.verifier = verifier or _stub_verifier
        self.tool_name = tool_name


# ---- 占位实现（跑通图用；单测可注入自定义）----

# _stub_planner 函数，产出最小 plan。
def _stub_planner(state: WorkflowState) -> dict[str, Any]:
    return {"objective": "reproduce controller", "steps": ["gen_code", "run"], "revision": len(state.plan.get("_history", []))}


# _stub_codegen 函数，产出最小 MATLAB 代码。
def _stub_codegen(state: WorkflowState) -> str:
    return "x = 2 + 2;\ndisp(x)\n"


# _stub_executor 函数，默认执行成功。
def _stub_executor(code: str, state: WorkflowState) -> tuple[bool, str, str, list[Artifact]]:
    return True, "4", "", []


# _stub_verifier 函数，默认判定：最近调用成功即通过（无验收标准时的行为）。
def _stub_verifier(state: WorkflowState) -> dict[str, Any]:
    last = state.latest_tool()
    passed = bool(last and last.ok)
    return {"passed": passed, "results": [], "summary": "ran_ok" if passed else "execution_failed"}


# ---- 节点函数 ----

# plan_node 函数，生成/修订执行计划。
def plan_node(state: WorkflowState, deps: NodeDeps) -> WorkflowState:
    state.plan = deps.planner(state)
    return state


# generate_node 函数，根据计划生成代码。
def generate_node(state: WorkflowState, deps: NodeDeps) -> WorkflowState:
    state.generated_code = deps.codegen(state)
    return state


# execute_node 函数，执行代码，登记 ToolCallRecord，失败则分类错误层级。
def execute_node(state: WorkflowState, deps: NodeDeps) -> WorkflowState:
    code = state.generated_code
    ok, stdout, stderr, artifacts = deps.executor(code, state)
    layer = classify_error(stderr, ok)
    record = ToolCallRecord(
        index=state.next_index(), tool_name=deps.tool_name,
        arguments={"code": code}, ok=ok, stdout=stdout, stderr=stderr,
        artifacts=artifacts, error_layer=layer,
    )
    state.tool_results.append(record)
    if not ok and layer is not None:
        state.errors.append(WorkflowErrorRecord(layer=layer, code="tool_failed", message=stderr[:200], tool_index=record.index))
    return state


# verify_node 函数，用注入的 verifier 做验收判定（跑通 + 指标达标）。
def verify_node(state: WorkflowState, deps: NodeDeps) -> WorkflowState:
    state.verdict = deps.verifier(state)
    passed = bool(state.verdict.get("passed"))
    state.verification_result = {
        "status": "verified" if passed else "criteria_not_met",
        "summary": state.verdict.get("summary", ""),
        "results": state.verdict.get("results", []),
    }
    return state


# finalize_node 函数，终态成功。
def finalize_node(state: WorkflowState) -> WorkflowState:
    state.status = "completed"
    state.verification_result.setdefault("status", "completed")
    return state


# finalize_failed_node 函数，终态失败。
def finalize_failed_node(state: WorkflowState) -> WorkflowState:
    state.status = "failed"
    err = state.latest_error()
    state.verification_result = {"status": "failed", "layer": err.layer if err else None}
    return state


# request_approval_node 函数，生成审批请求（占位：自动通过，真中断留待 M6）。
def request_approval_node(state: WorkflowState, auto_approve: bool = True) -> WorkflowState:
    last_code = state.generated_code
    state.approval_request = {"tool": "evaluate_matlab_code", "risk": "high", "code_preview": last_code[:200]}
    state.approval_status = "approved" if auto_approve else "pending"
    return state
