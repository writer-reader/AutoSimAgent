# 定义论文解析后的内部数据结构，并读取 MinerU JSON。
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.exceptions import ParseError


# PaperBlock 类，封装该模块中的相关状态与行为。
class PaperBlock(BaseModel):
    block_id: str
    type: Literal["paragraph", "equation", "table", "image"] = "paragraph"
    text: str = ""
    latex: str | None = None
    table_cells: list[list[str]] | None = None
    html: str | None = None          # 表格原始 HTML（MinerU table_body）
    caption: str | None = None       # 图/表标题
    image_path: str | None = None    # 图片相对路径
    page_idx: int | None = None      # 所在页码（0 基）
    evidence_ref: str | None = None


# PaperSection 类，封装该模块中的相关状态与行为。
class PaperSection(BaseModel):
    section_id: str
    heading: str
    level: int = 1
    page_range: tuple[int, int] | None = None
    blocks: list[PaperBlock] = Field(default_factory=list)


# ParsedPaper 类，封装该模块中的相关状态与行为。
class ParsedPaper(BaseModel):
    paper_id: str
    title: str = ""
    sections: list[PaperSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


# parse_mineru_json 函数，解析输入数据并转换为内部结构。
def parse_mineru_json(json_path: str | Path) -> ParsedPaper:
    path = Path(json_path)
    if not path.exists():
        raise ParseError("mineru_json_missing", "MinerU JSON file does not exist", {"file": path.name})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseError("mineru_json_invalid", "MinerU JSON could not be parsed", {"file": path.name}) from exc

    # 真实 MinerU content_list.json 是「块数组」；旧格式是完整 ParsedPaper 字典。
    if isinstance(data, list):
        from app.ingestion.adapter import content_list_to_paper  # 延迟导入避免循环

        paper_id = path.stem.replace("_content_list", "").replace("_content", "")
        return content_list_to_paper(data, paper_id=paper_id)
    try:
        return ParsedPaper.model_validate(data)
    except ValueError as exc:
        raise ParseError("mineru_json_invalid", "MinerU JSON could not be parsed", {"file": path.name}) from exc
