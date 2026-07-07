# 端到端联网跑通脚本：导入 PDF → MinerU 云解析 → adapter → LLM 知识抽取。
# 用法: python scripts/run_ingest.py "<pdf路径>"
# 可断点续跑：若 data/mineru/{paper_id}/ 已有 content_list.json 则跳过 MinerU 重解析。
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config_loader import load_config, validate_required_secrets
from app.ingestion.adapter import mineru_output_to_paper, save_parsed_paper
from app.ingestion.downloader import PaperSource, import_local_pdf
from app.ingestion.mineru_client import MineruClient, MineruResult
from app.knowledge.llm_extractor import LlmKnowledgeExtractor
from app.knowledge.postprocessor import merge_knowledge, save_merged_knowledge
from app.llm.client import LLMClient


def main(pdf_path: str) -> None:
    cfg = load_config("configs")
    validate_required_secrets(cfg)
    print(f"[0] config loaded; base_url={cfg.model.base_url} model={cfg.model.default_llm}")

    # [1] 导入归档
    dl = import_local_pdf(PaperSource(local_path=pdf_path), max_size_mb=cfg.mineru.max_pdf_size_mb)
    print(f"[1] imported: paper_id={dl.paper_id} -> {dl.pdf_path}")

    # [2] MinerU 云解析（可续跑）
    existing = Path("data/mineru") / dl.paper_id
    content_list = next(existing.rglob("*content_list.json"), None) if existing.exists() else None
    if content_list:
        print(f"[2] reuse existing MinerU output: {content_list}")
        md = next(existing.rglob("*.md"), None)
        mineru = MineruResult(dl.paper_id, str(md or ""), str(content_list), str(existing / "images"))
    else:
        print("[2] calling MinerU cloud API (may take minutes) ...")
        mineru = MineruClient(cfg.mineru).parse_pdf(dl.paper_id, dl.pdf_path)
        print(f"[2] MinerU done: {mineru.content_list_path}")

    # [3] adapter → ParsedPaper（并持久化，供 codegen 顺 evidence_ref 检索原文）
    paper = mineru_output_to_paper(mineru.content_list_path, paper_id=dl.paper_id)
    parsed_path = save_parsed_paper(paper)
    n_blocks = sum(len(s.blocks) for s in paper.sections)
    print(f"[3] parsed: title={paper.title!r} sections={len(paper.sections)} blocks={n_blocks} saved={parsed_path}")

    # [4] LLM 知识抽取（联网）
    print("[4] LLM knowledge extraction ...")
    llm = LLMClient(cfg.model)
    eqs, ctrls, params, criteria = LlmKnowledgeExtractor(llm).extract(paper, criteria_samples=cfg.knowledge.criteria_samples)
    merged = merge_knowledge(dl.paper_id, eqs, ctrls, params, cfg.knowledge.confidence_threshold, criteria=criteria)
    out = save_merged_knowledge(merged)
    print(f"[4] extracted: equations={len(eqs)} controllers={len(ctrls)} parameters={len(params)} criteria={len(criteria)}")
    print(f"[4] needs_review={len(merged.needs_review)}  saved={out}")
    for c in criteria:
        print(f"      criterion: {c.metric} [{c.relation} {c.expected}] {c.description[:50]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/run_ingest.py <pdf_path>")
        raise SystemExit(2)
    main(sys.argv[1])
