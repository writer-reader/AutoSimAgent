# 工作流节点实现。节点先以「可注入依赖」形式落地：
# 默认占位逻辑用于跑通图与分层路由单测；后续把 planner/codegen/executor 换成真实 LLM/MCP。
from __future__ import annotations

from typing import Any, Callable, Protocol

from langgraph.types import interrupt

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


# ReExtractor 协议，L4 回滚时重新抽取知识，返回更新后的 state。
class ReExtractor(Protocol):
    def __call__(self, state: WorkflowState) -> WorkflowState: ...


# NodeDeps 类，聚合节点的可注入依赖。
class NodeDeps:
    # __init__ 方法，注入 planner/codegen/executor/verifier/re_extractor（缺省用占位实现）。
    def __init__(
        self,
        planner: Planner | None = None,
        codegen: CodeGen | None = None,
        executor: Executor | None = None,
        verifier: Verifier | None = None,
        re_extractor: ReExtractor | None = None,
        tool_name: str = "evaluate_matlab_code",
    ) -> None:
        self.planner = planner or _stub_planner
        self.codegen = codegen or _stub_codegen
        self.executor = executor or _stub_executor
        self.verifier = verifier or _stub_verifier
        self.re_extractor = re_extractor  # None = 降级到纯反馈模式
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


# extract_knowledge_node 函数，L4 回滚：尝试重新抽取知识。
# 有 re_extractor 时真实重抽（降低置信度阈值 + 增加采样数）；
# 无 re_extractor 时退为反馈模式，在 plan._error_feedback 中注入提示，
# 让 planner 下轮用工程估算值弥补知识缺口，而不是原地空转。
def extract_knowledge_node(state: WorkflowState, deps: NodeDeps) -> WorkflowState:
    if deps.re_extractor is not None:
        state = deps.re_extractor(state)
    else:
        feedback = (
            "\n[L4 知识缺口] 本轮因知识级错误回滚，原始知识抽取可能不完整。"
            "请在规划时：①对缺失参数使用控制工程常用估算值；"
            "②简化模型结构；③在代码注释中标明估算依据。"
        )
        existing = state.plan.get("_error_feedback") or ""
        state.plan = {**state.plan, "_error_feedback": existing + feedback}
    return state


# request_verification_approval_node 函数，verify 通过后可选的人工确认。
# auto_approve=True 时直接放行；False 时 interrupt，让用户查看判定结果后决定。
# resume 时 interrupt() 返回 {"approved": bool}：
#   approved=True  → finalize（接受复现结果）
#   approved=False → 退回 generate，重新迭代（相当于额外一轮校准）
def request_verification_approval_node(state: WorkflowState, auto_approve: bool = True) -> WorkflowState:
    if auto_approve:
        state.verification_approval_status = "approved"
        return state
    last = state.latest_tool()
    artifacts = [a.model_dump() for a in (last.artifacts if last else [])]
    payload = {
        "type": "verification",
        "summary": state.verdict.get("summary", ""),
        "results": state.verdict.get("results", []),
        "code_paths": state.generated_code_paths[-1:],
        "artifacts": artifacts[:6],
        "calib_rounds": state.retries.calib,
    }
    decision: dict = interrupt(payload)
    state.verification_approval_status = "approved" if decision.get("approved", True) else "rejected"
    return state
# auto_approve=True 时自动通过（批量/CI 模式）；
# auto_approve=False 时调用 LangGraph interrupt()，图暂停并把代码预览推给调用方，
# resume 时 interrupt() 返回 {"approved": bool, "edited_code": str|None}。
def request_approval_node(state: WorkflowState, auto_approve: bool = True) -> WorkflowState:
    last_code = state.generated_code
    payload = {
        "tool": "evaluate_matlab_code",
        "language": "matlab",
        "code": last_code,                      # 完整代码（前端 Monaco 编辑器使用）
        "interrupt_key": f"approval_{state.task_id}_{len(state.tool_results)}",
        # 以下字段供后端逻辑使用，前端不展示
        "code_len": len(last_code),
        "retry_counts": state.retries.model_dump(),
    }
    state.approval_request = payload
    if auto_approve:
        state.approval_status = "approved"
        return state
    # 真中断：图在此暂停，等待 Command(resume={...}) 恢复。
    decision: dict = interrupt(payload)
    if decision.get("edited_code"):
        state.generated_code = decision["edited_code"]
    state.approval_status = "approved" if decision.get("approved", False) else "rejected"
    return state
