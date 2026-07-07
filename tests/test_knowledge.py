# 测试 LLM 知识抽取服务（用假 LLM，离线）。
from __future__ import annotations

import json

from app.ingestion.parser import PaperBlock, PaperSection, ParsedPaper
from app.llm.client import LLMClient
from app.services.knowledge_service import KnowledgeService
from tests.conftest import FakeChatClient


def _paper() -> ParsedPaper:
    return ParsedPaper(
        paper_id="paper_abc",
        sections=[PaperSection(section_id="sec_1", heading="Controller", blocks=[
            PaperBlock(block_id="b1", type="equation", latex="u = -kx", evidence_ref="sec_1.block_0"),
            PaperBlock(block_id="b2", text="The controller uses k = 2.", evidence_ref="sec_1.block_1"),
        ])],
    )


# test_knowledge_service_maps_llm_output 测试抽取→严格schema→合并→落盘。
def test_knowledge_service_maps_llm_output(tmp_path, monkeypatch, fake_model_config) -> None:
    monkeypatch.chdir(tmp_path)
    canned = json.dumps({
        "equations": [{"latex": "u = -kx", "category": "controller", "evidence_ref": "sec_1.block_0", "confidence": 0.9}],
        "controllers": [{"type": "PID", "architecture": "state feedback", "evidence_ref": "sec_1.block_0", "confidence": 0.8}],
        "parameters": [{"symbol": "k", "value": 2, "belongs_to": "controller", "evidence_ref": "sec_1.block_1", "confidence": 0.5}],
        "criteria": [{"metric": "tracking_error", "description": "误差趋于0", "relation": "approx_zero", "tolerance": 0.01, "evidence_ref": "sec_1.block_0", "confidence": 0.9}],
    })
    llm = LLMClient(fake_model_config, client=FakeChatClient([canned]))
    result = KnowledgeService(llm, confidence_threshold=0.75, criteria_samples=1).build(_paper())

    assert result.equation_count == 1
    assert result.controller_count == 1
    assert result.parameter_count == 1
    assert result.criteria_count == 1
    # k 的 confidence 0.5 < 0.75 → needs_review
    assert result.needs_review_count == 1
    saved = json.loads(open(result.merged_path, encoding="utf-8").read())
    assert saved["equations"][0]["equation_id"] == "eq_paper_abc_0"
    assert saved["criteria"][0]["criterion_id"] == "crit_paper_abc_0"
