# 测试图路由：工具审批、分层错误分类与阶梯回滚。
from __future__ import annotations

from app.graph.router import classify_error, route_after_approval, route_after_error, route_tool_call
from app.graph.state import ToolCallRecord, WorkflowState


def _state(**kw) -> WorkflowState:
    return WorkflowState(trace_id="t", task_id="task", paper_id="paper", **kw)


# test_high_risk_tools_route_to_approval 测试高风险工具走审批。
def test_high_risk_tools_route_to_approval() -> None:
    assert route_tool_call("evaluate_matlab_code") == "request_approval"
    assert route_tool_call("model_edit") == "request_approval"
    assert route_tool_call("model_read") == "execute_tool"


# test_classify_error_layers 测试错误分层识别。
def test_classify_error_layers() -> None:
    assert classify_error("", True) is None
    assert classify_error("connection timed out", False) == "L1"
    assert classify_error("Undefined function 'foo'", False) == "L2"
    assert classify_error("solver did not converge", False) == "L3"
    assert classify_error("missing parameter Kp", False) == "L4"


# test_successful_tool_routes_to_verify 测试最近调用成功则前进。
def test_successful_tool_routes_to_verify() -> None:
    state = _state()
    state.tool_results.append(ToolCallRecord(index=0, tool_name="x", ok=True))
    assert route_after_error(state) == "verify"


# test_l2_error_routes_to_generate_within_budget 测试 L2 预算内回 generate。
def test_l2_error_routes_to_generate_within_budget() -> None:
    state = _state()
    state.tool_results.append(ToolCallRecord(index=0, tool_name="x", ok=False, stderr="syntax error", error_layer="L2"))
    assert route_after_error(state) == "generate"
    assert state.retries.l2 == 1


# test_layer_escalation_to_failure 测试逐层升级直至失败。
def test_layer_escalation_to_failure() -> None:
    state = _state()
    state.tool_results.append(ToolCallRecord(index=0, tool_name="x", ok=False, stderr="syntax error", error_layer="L2"))
    targets = [route_after_error(state) for _ in range(6)]
    # L2×2 -> generate,generate; L3×1 -> plan; L4×1 -> extract_knowledge; 之后 finalize_failed
    assert targets[0] == "generate" and targets[1] == "generate"
    assert "plan" in targets and "extract_knowledge" in targets
    assert targets[-1] == "finalize_failed"


# test_rejected_approval_routes_to_plan 测试审批拒绝回规划。
def test_rejected_approval_routes_to_plan() -> None:
    state = _state()
    state.approval_status = "rejected"
    assert route_after_approval(state) == "plan"
