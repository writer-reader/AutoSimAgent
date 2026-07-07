# 测试 MinerU content_list.json → ParsedPaper 适配器。
from __future__ import annotations

from app.ingestion.adapter import content_list_to_paper


def _items():
    return [
        {"type": "text", "text": "A Robust Controller", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "Intro text", "page_idx": 0},
        {"type": "text", "text": "Design", "text_level": 1, "page_idx": 1},
        {"type": "equation", "text": "\\dot{x}=Ax", "text_format": "latex", "page_idx": 1},
        {"type": "table", "table_body": "<table></table>", "table_caption": ["T1"], "page_idx": 1},
        {"type": "image", "img_path": "images/f.jpg", "img_caption": ["Fig"], "page_idx": 2},
        {"type": "chart", "img_path": "images/c.jpg", "page_idx": 2},
        {"type": "footer", "text": "noise", "page_idx": 2},
        {"type": "page_number", "text": "3", "page_idx": 2},
        {"type": "text", "text": "", "page_idx": 2},
    ]


# test_adapter_builds_sections_with_evidence 测试 section 层级与证据锚点。
def test_adapter_builds_sections_with_evidence() -> None:
    paper = content_list_to_paper(_items(), paper_id="paper_x")
    assert paper.title == "A Robust Controller"
    headings = [s.heading for s in paper.sections]
    assert "Design" in headings
    blocks = [b for s in paper.sections for b in s.blocks]
    types = {b.type for b in blocks}
    assert "equation" in types and "table" in types and "image" in types
    # equation 带 latex
    eq = next(b for b in blocks if b.type == "equation")
    assert eq.latex == "\\dot{x}=Ax" and eq.evidence_ref
    # chart 归为 image
    assert sum(1 for b in blocks if b.type == "image") == 2


# test_adapter_filters_noise_and_empty 测试噪声与空块被过滤。
def test_adapter_filters_noise_and_empty() -> None:
    paper = content_list_to_paper(_items(), paper_id="paper_x")
    para_texts = [b.text for s in paper.sections for b in s.blocks if b.type == "paragraph"]
    assert "noise" not in para_texts   # footer 被过滤
    assert "3" not in para_texts        # page_number 被过滤
    assert "" not in para_texts         # 空正文段落被丢弃
    # 图片块允许空 caption，但不应有空文本的段落块
    assert all(t.strip() for t in para_texts)
