# 测试验收标准穷尽多采样 + 归并去重（治非确定性）。
from __future__ import annotations

import json

from app.knowledge.llm_extractor import LlmKnowledgeExtractor
from app.llm.client import LLMClient
from tests.conftest import FakeChatClient


def _crit(metric, rel="approx_zero", ev="section_1.block_0"):
    return {"metric": metric, "description": f"desc {metric}", "relation": rel, "evidence_ref": ev, "confidence": 0.9}


# test_extract_criteria_union_then_consolidate 测试多采样并集→归并→去重。
def test_extract_criteria_union_then_consolidate(fake_model_config) -> None:
    # 两次采样各挑不同子集（模拟非确定性），归并成全覆盖
    sample1 = json.dumps({"criteria": [_crit("freq_error"), _crit("settling_time", "less_than")]})
    sample2 = json.dumps({"criteria": [_crit("power_error"), _crit("freq_error")]})  # freq_error 重复
    consolidated = json.dumps({"criteria": [
        _crit("freq_error"), _crit("settling_time", "less_than"), _crit("power_error"),
    ]})
    fake = FakeChatClient([sample1, sample2, consolidated])
    ext = LlmKnowledgeExtractor(LLMClient(fake_model_config, client=fake))
    crits = ext.extract_criteria("paper_x", "paper text", samples=2)
    metrics = [c.metric for c in crits]
    # 全覆盖且去重：3 条不同命题
    assert set(metrics) == {"freq_error", "settling_time", "power_error"}
    assert len(metrics) == 3
    assert crits[0].criterion_id == "crit_paper_x_0"


# test_extract_criteria_dedup_by_metric 测试归并结果仍按 metric 名兜底去重。
def test_extract_criteria_dedup_by_metric(fake_model_config) -> None:
    s1 = json.dumps({"criteria": [_crit("freq_error")]})
    s2 = json.dumps({"criteria": [_crit("freq_error")]})
    # 归并 LLM 意外返回重复
    cons = json.dumps({"criteria": [_crit("freq_error"), _crit("FREQ_ERROR")]})
    fake = FakeChatClient([s1, s2, cons])
    ext = LlmKnowledgeExtractor(LLMClient(fake_model_config, client=fake))
    crits = ext.extract_criteria("p", "t", samples=2)
    assert len(crits) == 1   # freq_error 与 FREQ_ERROR 视为同一（大小写归一）


# test_single_sample_skips_consolidation 测试 samples<=1 不做归并（省调用）。
def test_single_sample_skips_consolidation(fake_model_config) -> None:
    s1 = json.dumps({"criteria": [_crit("freq_error"), _crit("power_error")]})
    fake = FakeChatClient([s1])   # 只需1次调用
    ext = LlmKnowledgeExtractor(LLMClient(fake_model_config, client=fake))
    crits = ext.extract_criteria("p", "t", samples=1)
    assert {c.metric for c in crits} == {"freq_error", "power_error"}
    assert len(fake.calls) == 1   # 无归并调用
