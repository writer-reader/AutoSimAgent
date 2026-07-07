# 顺 evidence_ref 锚点从 ParsedPaper 检索论文原文（结构化锚点检索，非向量 RAG）。
# 供 codegen 拿到论文真实推导（尤其稳定性/裕度分析），补"只有结论、没有方法"的缺口。
from __future__ import annotations

from app.ingestion.parser import ParsedPaper, PaperSection


# _section_id_of 函数，从 "section_7.block_3" 取出 "section_7"。
def _section_id_of(ref: str) -> str:
    return ref.split(".", 1)[0] if ref else ""


# resolve_sections 函数，把一组 evidence_ref 解析为其所属 section（保持论文顺序、去重）。
def resolve_sections(paper: ParsedPaper, refs: list[str]) -> list[PaperSection]:
    wanted = {_section_id_of(r) for r in refs if r and r != "unknown"}
    return [s for s in paper.sections if s.section_id in wanted]


# _render_section 函数，把一个 section 渲染为带公式的可读文本（跳过图/表视觉块）。
def _render_section(sec: PaperSection) -> str:
    lines = [f"## {sec.heading}"]
    for b in sec.blocks:
        if b.type == "equation":
            lines.append(f"$$ {b.latex or b.text} $$")
        elif b.type in ("image", "table"):
            continue
        elif b.text.strip():
            lines.append(b.text.strip())
    return "\n".join(lines)


# build_source_excerpt 函数，按 evidence_ref 拼装聚焦的论文原文摘录（含推导上下文）。
def build_source_excerpt(paper: ParsedPaper, refs: list[str], max_chars: int = 14000) -> str:
    secs = resolve_sections(paper, refs)
    if not secs:
        return ""
    return "\n\n".join(_render_section(s) for s in secs)[:max_chars]
