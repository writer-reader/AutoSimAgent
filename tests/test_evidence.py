# 测试 evidence_ref 锚点检索原文 + codegen 注入原文摘录。
from __future__ import annotations

from app.graph.real_nodes import RealCodeGen, _source_excerpt_for
from app.graph.state import WorkflowState
from app.ingestion.adapter import load_parsed_paper, save_parsed_paper
from app.ingestion.parser import PaperBlock, PaperSection, ParsedPaper
from app.knowledge.evidence import build_source_excerpt, resolve_sections
from app.llm.client import LLMClient
from tests.conftest import FakeChatClient


def _paper() -> ParsedPaper:
    return ParsedPaper(paper_id="paper_x", title="T", sections=[
        PaperSection(section_id="section_1", heading="Intro", blocks=[
            PaperBlock(block_id="b0", type="paragraph", text="背景。", evidence_ref="section_1.block_0"),
        ]),
        PaperSection(section_id="section_7", heading="Stability Analysis", blocks=[
            PaperBlock(block_id="b0", type="paragraph", text="由定理2，稳定当且仅当...", evidence_ref="section_7.block_0"),
            PaperBlock(block_id="b1", type="equation", latex="\\tau_{max}=\\pi/(2 m \\lambda_{max})", evidence_ref="section_7.block_1"),
        ]),
    ])


# test_resolve_sections 测试锚点解析到 section（去重、保序）。
def test_resolve_sections() -> None:
    secs = resolve_sections(_paper(), ["section_7.block_1", "section_7.block_0", "unknown", ""])
    assert [s.section_id for s in secs] == ["section_7"]


# test_build_excerpt_includes_derivation 测试摘录含推导文本与公式，跳过无关 section。
def test_build_excerpt_includes_derivation() -> None:
    ex = build_source_excerpt(_paper(), ["section_7.block_1"])
    assert "Stability Analysis" in ex
    assert "定理2" in ex
    assert "tau_{max}" in ex or "\\tau_{max}" in ex
    assert "Intro" not in ex   # 未被引用的 section 不含


# test_save_load_parsed_paper 测试 ParsedPaper 持久化往返。
def test_save_load_parsed_paper(tmp_path) -> None:
    p = save_parsed_paper(_paper(), output_dir=str(tmp_path))
    back = load_parsed_paper(p)
    assert back.paper_id == "paper_x" and len(back.sections) == 2


# test_codegen_injects_source_excerpt 测试 codegen 顺 parsed_doc_ref 注入原文。
def test_codegen_injects_source_excerpt(tmp_path, fake_model_config) -> None:
    parsed_path = save_parsed_paper(_paper(), output_dir=str(tmp_path))
    fake = FakeChatClient(["x = 1;"])
    codegen = RealCodeGen(LLMClient(fake_model_config, client=fake))
    state = WorkflowState(trace_id="t", task_id="x", paper_id="paper_x",
                          parsed_doc_ref=parsed_path, plan={"objective": "repro"},
                          acceptance_criteria=[{"metric": "m", "evidence_ref": "section_7.block_1"}])
    codegen(state)
    # 发给 LLM 的 prompt 里应含被检索的稳定性分析原文
    sent_prompt = fake.calls[0]["messages"][-1]["content"]
    assert "Stability Analysis" in sent_prompt
    assert "定理2" in sent_prompt


# test_source_excerpt_graceful_degrade 测试 parsed_doc_ref 缺失时优雅降级。
def test_source_excerpt_graceful_degrade() -> None:
    state = WorkflowState(trace_id="t", task_id="x", paper_id="p", parsed_doc_ref="/nonexistent.json")
    assert _source_excerpt_for(state) == ""
