# 测试真实节点：RealExecutor 的代码落盘与 figure 目录扫描（用假 MATLAB 客户端）。
from __future__ import annotations

from pathlib import Path

from app.graph.real_nodes import RealCodeGen, RealExecutor, RealPlanner
from app.graph.state import WorkflowState
from app.llm.client import LLMClient
from app.tools.matlab_mcp import MatlabMcpClient, MatlabRunResult
from tests.conftest import FakeChatClient


# FakeMatlab 类，模拟 MATLAB MCP：执行文件时在 outdir 生成一张假图。
class FakeMatlab(MatlabMcpClient):
    def __init__(self, make_fig: bool = True) -> None:
        self.make_fig = make_fig
        self.ran: list[str] = []

    def run_file(self, script_path: str) -> MatlabRunResult:
        self.ran.append(script_path)
        if self.make_fig:
            (Path(script_path).parent / "fig_1.png").write_bytes(b"\x89PNG")
        return MatlabRunResult(ok=True, stdout="done", stderr="")


# test_executor_scans_figures 测试执行后扫描到新 figure 并登记 artifact。
def test_executor_scans_figures(tmp_path) -> None:
    ex = RealExecutor(FakeMatlab(make_fig=True), work_root=str(tmp_path / "gen"))
    state = WorkflowState(trace_id="t", task_id="task_fig", paper_id="p")
    state.generated_code = "plot(1:10)"
    ok, stdout, stderr, artifacts = ex(state.generated_code, state)
    assert ok and stdout == "done"
    assert len(artifacts) == 1 and artifacts[0].kind == "figure"
    assert artifacts[0].path.endswith("fig_1.png")
    # 代码已落盘
    assert state.generated_code_paths and Path(state.generated_code_paths[0]).exists()


# test_executor_no_artifacts_when_none 测试无新文件时不误报 artifact。
def test_executor_no_artifacts_when_none(tmp_path) -> None:
    ex = RealExecutor(FakeMatlab(make_fig=False), work_root=str(tmp_path / "gen"))
    state = WorkflowState(trace_id="t", task_id="task_none", paper_id="p")
    ok, _, _, artifacts = ex("x=1;", state)
    assert ok and artifacts == []


# test_planner_and_codegen_parse 测试 planner/codegen 解析 LLM 文本输出。
def test_planner_and_codegen_parse(fake_model_config) -> None:
    plan_llm = LLMClient(fake_model_config, client=FakeChatClient(['{"objective":"repro","steps":["a"]}']))
    plan = RealPlanner(plan_llm)(WorkflowState(trace_id="t", task_id="x", paper_id="p"))
    assert plan["objective"] == "repro"

    code_llm = LLMClient(fake_model_config, client=FakeChatClient(["```matlab\nx=2+2;\n```"]))
    st = WorkflowState(trace_id="t", task_id="x", paper_id="p", plan=plan)
    code = RealCodeGen(code_llm)(st)
    assert "x=2+2" in code and "```" not in code  # 代码围栏被剥离
