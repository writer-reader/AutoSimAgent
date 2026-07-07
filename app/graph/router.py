# 定义工具调用路由、分层错误分类与回滚决策。
from __future__ import annotations

import re

from app.graph.state import ErrorLayer, WorkflowState

# 高风险工具（需人工审批），与 configs/matlab.yaml、simulink.yaml 对齐。
HIGH_RISK_TOOLS = {"evaluate_matlab_code", "run_matlab_file", "model_edit", "model_test"}

# 每层重试预算：L1 瞬时×2 / L2 代码级×2 / L3 方案级×1 / L4 知识级×1。
RETRY_BUDGET = {"L1": 2, "L2": 2, "L3": 1, "L4": 1}

# 结果校准预算：跑通但指标不达标时，回 codegen 调整的最大轮数（比纯代码错多给，调对结果更难）。
CALIB_BUDGET = 4

# L1 瞬时错误特征（可纯重试）。
_L1_PATTERNS = [r"timed?\s*out", r"timeout", r"connection", r"busy", r"temporarily", r"ECONN", r"mcp_not_started"]
# L2 代码级错误特征（回 generate 改代码）。
_L2_PATTERNS = [
    r"undefined function", r"undefined variable", r"unrecognized", r"syntax error",
    r"too many (?:input|output)", r"not enough input", r"index exceeds",
    r"undefined near", r"invalid use", r"error using", r"dimension", r"nonconformant",
]
# L3 方案级错误特征（回 plan 重规划）。
_L3_PATTERNS = [r"did not converge", r"not converge", r"unstable", r"infeasible", r"block .* not found", r"does not exist"]
# L4 知识级错误特征（回知识抽取）。
_L4_PATTERNS = [r"missing parameter", r"no parameter", r"unknown model", r"knowledge", r"no equation"]


# classify_error 函数，根据 stderr 文本判定错误层级。
def classify_error(stderr: str, ok: bool) -> ErrorLayer | None:
    if ok:
        return None
    text = (stderr or "").lower()
    if not text.strip():
        return "L2"  # 失败但无信息，保守当代码级
    for pat in _L1_PATTERNS:
        if re.search(pat, text):
            return "L1"
    for pat in _L4_PATTERNS:
        if re.search(pat, text):
            return "L4"
    for pat in _L3_PATTERNS:
        if re.search(pat, text):
            return "L3"
    for pat in _L2_PATTERNS:
        if re.search(pat, text):
            return "L2"
    return "L2"  # 兜底：未知运行错按代码级处理


# _budget_of 函数，取某层已用重试次数。
def _budget_of(state: WorkflowState, layer: ErrorLayer) -> int:
    return {"L1": state.retries.l1, "L2": state.retries.l2, "L3": state.retries.l3, "L4": state.retries.l4}.get(layer, 0)


# _bump 函数，某层重试计数 +1。
def _bump(state: WorkflowState, layer: ErrorLayer) -> None:
    if layer == "L1":
        state.retries.l1 += 1
    elif layer == "L2":
        state.retries.l2 += 1
    elif layer == "L3":
        state.retries.l3 += 1
    elif layer == "L4":
        state.retries.l4 += 1


# _escalate 函数，把层级升一级（L2→L3→L4→L5）。
_ESCALATE = {"L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5", "L5": "L5"}


# route_tool_call 函数，判断工具是否需人工审批。
# 首次执行高风险工具走审批；已审批过（approval_status="approved"）说明是重试，直接执行。
def route_tool_call(tool_name: str, state: WorkflowState | None = None) -> str:
    if tool_name not in HIGH_RISK_TOOLS:
        return "execute_tool"
    if state is not None and state.approval_status == "approved":
        return "execute_tool"   # 重试路径：前序审批已通过，无需再次打断用户
    return "request_approval"


# 层级 → 回滚目标节点。
_LAYER_TARGET = {"L1": "execute", "L2": "generate", "L3": "plan", "L4": "extract_knowledge"}


# route_after_error 函数，分层回滚决策：返回下一个节点名。
# budget 参数由 workflow 从 GraphConfig 注入；缺省用模块常量（向后兼容）。
def route_after_error(state: WorkflowState, budget: dict | None = None) -> str:
    _budget = budget or RETRY_BUDGET
    last = state.latest_tool()
    if last is None or last.ok:
        return "verify"
    cur: ErrorLayer = last.error_layer or "L2"
    while cur != "L5":
        if _budget_of(state, cur) < _budget.get(cur, 0):
            _bump(state, cur)
            return _LAYER_TARGET[cur]
        cur = _ESCALATE[cur]  # type: ignore[assignment]
    return "finalize_failed"


# route_after_verify 函数，验收判定后决策：达标→finalize，未达标且有预算→回 generate 校准，否则失败。
# 当 require_verification_approval=True 时，通过的结果先走人工确认再 finalize。
def route_after_verify(
    state: WorkflowState,
    require_verification_approval: bool = False,
    calib_budget: int = CALIB_BUDGET,
) -> str:
    verdict = state.verdict or {}
    if verdict.get("passed"):
        if require_verification_approval:
            return "request_verification_approval"
        return "finalize"
    if state.retries.calib < calib_budget:
        state.retries.calib += 1
        return "generate"
    return "finalize_failed"


# route_after_approval 函数，审批结果 → 下一步。
def route_after_approval(state: WorkflowState) -> str:
    if state.approval_status == "approved":
        return "execute_tool"
    if state.approval_status == "rejected":
        return "plan"  # 拒绝 → 回规划
    return "request_approval"  # 仍 pending（真中断场景）
