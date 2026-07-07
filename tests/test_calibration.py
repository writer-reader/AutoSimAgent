# 测试结果校准：RealVerifier 数值比对 + LLM判模糊项；校准回滚循环。
from __future__ import annotations

from app.graph.nodes import NodeDeps
from app.graph.real_nodes import RealVerifier, _literal_leak_check, _sanitize_desc
from app.graph.state import Artifact, ToolCallRecord, WorkflowState
from app.graph.workflow import ControlWorkflow
from app.llm.client import LLMClient
from tests.conftest import FakeChatClient


def _state_with_metrics(criteria, metrics, ok=True):
    s = WorkflowState(trace_id="t", task_id="x", paper_id="p",
                      acceptance_criteria=criteria, computed_metrics=metrics)
    s.tool_results.append(ToolCallRecord(index=0, tool_name="run_matlab_file", ok=ok, stdout="done"))
    return s


# test_verifier_numeric_pass 测试数值指标达标判过。
def test_verifier_numeric_pass(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient([])))
    crit = [{"metric": "freq_error", "relation": "approx_zero", "tolerance": 0.01}]
    verdict = v(_state_with_metrics(crit, {"freq_error": 0.005}))
    assert verdict["passed"] is True
    assert verdict["results"][0]["passed"] is True


# test_verifier_numeric_fail 测试数值超容差判败。
def test_verifier_numeric_fail(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient([])))
    crit = [{"metric": "freq_error", "relation": "approx_zero", "tolerance": 0.01}]
    verdict = v(_state_with_metrics(crit, {"freq_error": 3.2}))
    assert verdict["passed"] is False
    assert verdict["results"][0]["actual"] == 3.2


# test_verifier_less_than 测试 less_than 关系。
def test_verifier_less_than(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient([])))
    crit = [{"metric": "delay_margin", "relation": "less_than", "expected": 0.01}]
    assert v(_state_with_metrics(crit, {"delay_margin": 0.0076}))["passed"] is True
    assert v(_state_with_metrics(crit, {"delay_margin": 0.02}))["passed"] is False


# test_verifier_llm_judge_qualitative 测试定性命题交 LLM 判。
def test_verifier_llm_judge_qualitative(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient(['{"passed":true,"reason":"曲线收敛"}'])))
    crit = [{"metric": "convergence", "relation": "converges", "description": "频率曲线收敛"}]
    verdict = v(_state_with_metrics(crit, {}))
    assert verdict["passed"] is True
    assert "收敛" in verdict["results"][0]["reason"]


# test_verifier_execution_failed 测试执行失败直接判败。
def test_verifier_execution_failed(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient([])))
    verdict = v(_state_with_metrics([{"metric": "x", "relation": "approx_zero"}], {}, ok=False))
    assert verdict["passed"] is False and verdict["summary"] == "execution_failed"


# test_verifier_catches_hardcoded 测试防作弊：数值对但硬编码 → 判败。
def test_verifier_catches_hardcoded(fake_model_config) -> None:
    # 第1次调用=数值判(走代码不调LLM)；硬编码审查调LLM，返回该指标硬编码
    hc = '{"hardcoded":{"delay_margin":"直接赋值 = 7.6"}}'
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient([hc])))
    crit = [{"metric": "delay_margin", "relation": "equals", "expected": 7.6, "tolerance": 0.1}]
    s = _state_with_metrics(crit, {"delay_margin": 7.6})
    s.generated_code = "x = sin(1);  % 无泄露字面量"
    verdict = v(s)
    # 数值本来对(7.6==7.6)，但硬编码审查把它翻成 fail
    assert verdict["passed"] is False
    assert verdict["results"][0].get("hardcoded") is True
    assert "delay_margin" in verdict["hardcoded"]


# test_sanitize_desc 测试描述净化：抹掉等于期望值的数字（含单位换算）。
def test_sanitize_desc() -> None:
    assert "(值略)" in _sanitize_desc("computed as 7.6 ms", 7.6)
    assert "(值略)" in _sanitize_desc("margin is 0.0076 s", 7.6)   # ms↔s 换算
    assert "10" in _sanitize_desc("simulate for 10 seconds, margin 7.6", 7.6)  # 任务参数保留
    assert _sanitize_desc("error converges to zero", 0.0) == "error converges to zero"  # expected=0不动


# test_literal_leak_check 测试确定性字面量泄露检测（抓反推凑答案）。
def test_literal_leak_check() -> None:
    crit = [{"metric": "delay_margin_freq", "expected": 7.6},
            {"metric": "freq_error", "expected": 0.0}]
    # 代码含 7.6e-3（=7.6ms 的 s 值），应被抓
    code = "tau_target_f = 7.6e-3;\nw_f = fzero(@(w) maxeig(w)-lam, 1);\ntau_f = pi/(2*m*lambda);"
    flagged = _literal_leak_check(code, crit)
    assert "delay_margin_freq" in flagged
    assert "freq_error" not in flagged   # expected=0 不检测(太常见)
    # 干净代码不误报
    assert _literal_leak_check("lambda = max(eig(M)); tau = pi/(2*m*lambda);", crit) == {}


# test_verifier_catches_reverse_engineering 测试端到端抓反推（数值对+代码含字面量→fail）。
def test_verifier_catches_reverse_engineering(fake_model_config) -> None:
    v = RealVerifier(LLMClient(fake_model_config, client=FakeChatClient(['{"hardcoded":{}}'])))
    crit = [{"metric": "delay_margin_freq", "relation": "equals", "expected": 7.6, "tolerance": 0.1}]
    s = _state_with_metrics(crit, {"delay_margin_freq": 7.6})
    s.generated_code = "tau_target_f = 7.6e-3; w_f=fzero(...); tau_f=pi/(2*m*lam); delay_margin_freq=tau_f*1000;"
    verdict = v(s)
    # LLM 审查没抓到(返回空)，但确定性字面量检测抓到 7.6e-3
    assert verdict["passed"] is False
    assert "delay_margin_freq" in verdict["hardcoded"]


# test_calibration_rollback_then_pass 测试跑通但指标不达标→校准回generate→达标。
def test_calibration_rollback_then_pass() -> None:
    runs = {"n": 0}

    def executor(code, state):
        runs["n"] += 1
        # 第1次指标不达标，第2次达标
        state.computed_metrics = {"freq_error": 5.0 if runs["n"] < 2 else 0.001}
        return True, "done", "", []

    def verifier(state):
        v = state.computed_metrics.get("freq_error", 99)
        passed = abs(v) <= 0.01
        return {"passed": passed, "results": [{"metric": "freq_error", "actual": v, "passed": passed}],
                "summary": "1/1" if passed else "0/1"}

    wf = ControlWorkflow(NodeDeps(executor=executor, verifier=verifier))
    s = WorkflowState(trace_id="t", task_id="calib", paper_id="p",
                      acceptance_criteria=[{"metric": "freq_error", "relation": "approx_zero"}])
    final = wf.run(s)
    assert final.status == "completed"
    assert final.retries.calib == 1   # 校准了1轮
    assert runs["n"] == 2


# test_calibration_budget_exhausted 测试校准预算耗尽→失败。
def test_calibration_budget_exhausted() -> None:
    def executor(code, state):
        state.computed_metrics = {"freq_error": 9.9}
        return True, "done", "", []

    def verifier(state):
        return {"passed": False, "results": [{"metric": "freq_error", "actual": 9.9, "passed": False}], "summary": "0/1"}

    wf = ControlWorkflow(NodeDeps(executor=executor, verifier=verifier))
    s = WorkflowState(trace_id="t", task_id="calib_fail", paper_id="p",
                      acceptance_criteria=[{"metric": "freq_error", "relation": "approx_zero"}])
    final = wf.run(s, recursion_limit=100)
    assert final.status == "failed"
    assert final.retries.calib == 4   # CALIB_BUDGET
