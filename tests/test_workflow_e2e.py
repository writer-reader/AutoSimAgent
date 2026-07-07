# 测试真实 LangGraph 图：成功闭环、L2 重试、逐层升级失败、artifact 扫描。
from __future__ import annotations

from app.graph.nodes import NodeDeps
from app.graph.state import Artifact, WorkflowState
from app.graph.workflow import ControlWorkflow


def _state(tid: str) -> WorkflowState:
    return WorkflowState(trace_id="t", task_id=tid, paper_id="p")


# test_happy_path_completes 测试一次成功→verify→completed。
def test_happy_path_completes() -> None:
    wf = ControlWorkflow()
    final = wf.run(_state("ok"))
    assert final.status == "completed"
    assert final.verification_result["status"] == "verified"


# test_l2_retry_then_success 测试 L2 代码错重试后成功。
def test_l2_retry_then_success() -> None:
    calls = {"n": 0}

    def executor(code, state):
        calls["n"] += 1
        if calls["n"] < 3:
            return False, "", "Undefined function 'foo'", []
        return True, "ok", "", []

    wf = ControlWorkflow(NodeDeps(executor=executor))
    final = wf.run(_state("retry"))
    assert final.status == "completed"
    assert final.retries.l2 == 2
    assert calls["n"] == 3


# test_persistent_failure_escalates 测试持续失败逐层升级到 failed。
def test_persistent_failure_escalates() -> None:
    def executor(code, state):
        return False, "", "syntax error", []

    wf = ControlWorkflow(NodeDeps(executor=executor))
    final = wf.run(_state("fail"), recursion_limit=100)
    assert final.status == "failed"
    assert final.retries.l2 == 2 and final.retries.l3 == 1 and final.retries.l4 == 1


# test_artifacts_recorded 测试 figure artifact 进入 tool_results。
def test_artifacts_recorded() -> None:
    def executor(code, state):
        return True, "done", "", [Artifact(kind="figure", path="data/x/fig_1.png", label="resp")]

    wf = ControlWorkflow(NodeDeps(executor=executor))
    final = wf.run(_state("fig"))
    art = final.tool_results[-1].artifacts[0]
    assert art.kind == "figure" and art.path.endswith("fig_1.png")


# test_state_serializable 测试终态可序列化（checkpoint/API 兼容）。
def test_state_serializable() -> None:
    wf = ControlWorkflow()
    final = wf.run(_state("ser"))
    restored = WorkflowState.model_validate_json(final.model_dump_json())
    assert restored.status == "completed"
