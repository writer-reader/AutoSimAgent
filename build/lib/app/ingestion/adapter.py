# MinerU content_list.json → ParsedPaper 适配层。
# 将 MinerU 的「扁平块数组」按标题层级重组为带 section 层级与证据锚点的结构化文档，
# 供 LLM 直接消费（已去除 RAG 向量检索）。
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.exceptions import ParseError
from app.ingestion.parser import PaperBlock, PaperSection, ParsedPaper

# MinerU 版面噪声类型：页眉/页脚/页码等，不进入结构化文档。
_IGNORED_TYPES = {"footer", "header", "page_number", "page_footnote", "discarded"}


# _clean 函数，规整 caption 列表/字符串为单一文本。
def _clean(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value else ""


# _block_from_item 函数，将单个 content_list 条目转为 PaperBlock。
def _block_from_item(item: dict[str, Any], block_id: str, evidence_ref: str) -> PaperBlock | None:
    item_type = item.get("type", "text")
    page_idx = item.get("page_idx")
    if item_type == "equation":
        latex = item.get("text", "") or item.get("latex", "")
        return PaperBlock(
            block_id=block_id, type="equation", text=latex, latex=latex,
            page_idx=page_idx, evidence_ref=evidence_ref,
        )
    if item_type in ("image", "chart"):
        return PaperBlock(
            block_id=block_id, type="image",
            text=_clean(item.get("img_caption")),
            caption=_clean(item.get("img_caption")),
            image_path=item.get("img_path"),
            page_idx=page_idx, evidence_ref=evidence_ref,
        )
    if item_type == "table":
        return PaperBlock(
            block_id=block_id, type="table",
            text=_clean(item.get("table_caption")),
            caption=_clean(item.get("table_caption")),
            html=item.get("table_body"),
            page_idx=page_idx, evidence_ref=evidence_ref,
        )
    # 其余按文本处理（type=text 且无 text_level 的正文）
    text = item.get("text", "")
    if not text.strip():
        return None
    return PaperBlock(
        block_id=block_id, type="paragraph", text=text,
        page_idx=page_idx, evidence_ref=evidence_ref,
    )


# _is_heading 函数，判断条目是否为标题（MinerU 用 text_level 标注）。
def _is_heading(item: dict[str, Any]) -> bool:
    return item.get("type", "text") == "text" and bool(item.get("text_level"))


# content_list_to_paper 函数，将 MinerU content_list 数组转为 ParsedPaper。
def content_list_to_paper(
    items: list[dict[str, Any]],
    paper_id: str,
    title: str | None = None,
) -> ParsedPaper:
    sections: list[PaperSection] = []
    current: PaperSection | None = None
    seq = 0  # 全局块序号，保证 block_id 唯一

    def _open_section(heading: str, level: int) -> PaperSection:
        sec = PaperSection(section_id=f"section_{len(sections)}", heading=heading, level=level)
        sections.append(sec)
        return sec

    for item in items:
        if item.get("type") in _IGNORED_TYPES:
            continue  # 丢弃页眉/页脚/页码等版面噪声
        if _is_heading(item):
            heading = item.get("text", "").strip()
            level = int(item.get("text_level") or 1)
            current = _open_section(heading, level)
            continue
        if current is None:  # 首个标题前的内容归入前言 section
            current = _open_section("Preamble", 1)
        evidence_ref = f"{current.section_id}.block_{len(current.blocks)}"
        block = _block_from_item(item, block_id=f"block_{seq}", evidence_ref=evidence_ref)
        seq += 1
        if block is not None:
            current.blocks.append(block)

    # 补全每个 section 的页码范围
    for sec in sections:
        pages = [b.page_idx for b in sec.blocks if b.page_idx is not None]
        if pages:
            sec.page_range = (min(pages), max(pages))

    # 标题：优先入参，否则取首个 level==1 标题
    resolved_title = title or next(
        (s.heading for s in sections if s.level == 1 and s.heading and s.heading != "Preamble"),
        "",
    )
    return ParsedPaper(paper_id=paper_id, title=resolved_title, sections=sections)


# load_content_list 函数，从磁盘读取 MinerU content_list.json。
def load_content_list(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise ParseError("mineru_content_list_missing", "MinerU content_list.json not found", {"file": p.name})
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseError("mineru_content_list_invalid", "content_list.json is not valid JSON", {"file": p.name}) from exc
    if not isinstance(data, list):
        raise ParseError("mineru_content_list_invalid", "content_list.json must be a JSON array", {"file": p.name})
    return data


# mineru_output_to_paper 函数，从 MinerU 输出目录/文件构建 ParsedPaper。
def mineru_output_to_paper(content_list_path: str | Path, paper_id: str, title: str | None = None) -> ParsedPaper:
    return content_list_to_paper(load_content_list(content_list_path), paper_id=paper_id, title=title)


# save_parsed_paper 函数，持久化 ParsedPaper（供后续 evidence_ref 锚点检索原文）。
def save_parsed_paper(paper: ParsedPaper, output_dir: str | Path = "data/knowledge/parsed") -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{paper.paper_id}.json"
    path.write_text(paper.model_dump_json(indent=2), encoding="utf-8")
    return str(path)


# load_parsed_paper 函数，从磁盘加载 ParsedPaper。
def load_parsed_paper(path: str | Path) -> ParsedPaper:
    return ParsedPaper.model_validate_json(Path(path).read_text(encoding="utf-8"))
