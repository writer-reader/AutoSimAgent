# 透明化事件测试：on_progress 回调在节点完成时携带 plan/代码/工具结果/验收判定。
from __future__ import annotations

from app.graph.nodes import NodeDeps
from app.graph.state import Artifact, WorkflowState
from app.graph.workflow import ControlWorkflow


def _state(tid: str) -> WorkflowState:
    return WorkflowState(trace_id="t", task_id=tid, paper_id="p")


def test_transparent_done_events_carry_payload():
    """plan/generate/execute/verify 节点 done 事件应外发对应产物，而非只有 node 名。"""
    seen: list[tuple[str, dict]] = []

    def on_progress(stage: str, detail: dict) -> None:
        seen.append((stage, detail))

    def executor(code, state):
        return True, "stdout-xyz", "", [Artifact(kind="figure", path="data/x/fig_1.png", label="resp")]

    wf = ControlWorkflow(NodeDeps(executor=executor), on_progress=on_progress)
    final = wf.run(_state("transp"))
    assert final.status == "completed"

    done = {stage[:-5]: d for stage, d in seen if stage.endswith(":done")}
    # plan done 带 plan JSON
    assert "graph:plan" in done and "plan" in done["graph:plan"]
    # generate done 带代码
    assert "graph:generate" in done and "code" in done["graph:generate"]
    # execute done 带工具结果尾部与指标
    ex = done["graph:execute"]
    tr = ex["tool_result"]
    assert tr["ok"] is True and tr["stdout_tail"] == "stdout-xyz"
    assert any(a["path"].endswith("fig_1.png") for a in tr["artifacts"])
    # verify done 带 verdict
    assert "verdict" in done["graph:verify"]
