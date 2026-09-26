# 编排论文导入和 MinerU 解析流程。
from __future__ import annotations

from app.ingestion.adapter import mineru_output_to_paper
from app.ingestion.downloader import DownloadResult, PaperSource, import_local_pdf, import_uploaded_pdf
from app.ingestion.mineru_client import MineruClient, MineruResult
from app.ingestion.parser import ParsedPaper


# PaperService 类，封装该模块中的相关状态与行为。
class PaperService:
    # __init__ 方法，初始化实例依赖和默认参数。
    def __init__(self, mineru_client: MineruClient | None = None) -> None:
        self.mineru_client = mineru_client or MineruClient()

    # import_paper 函数，导入外部输入并生成系统内记录。
    def import_paper(self, source: PaperSource, max_size_mb: int = 100) -> DownloadResult:
        return import_local_pdf(source, max_size_mb=max_size_mb)

    # import_uploaded 函数，接收上传字节流写盘（浏览器文件选择器走此路径）。
    def import_uploaded(self, data: bytes, max_size_mb: int = 100) -> DownloadResult:
        return import_uploaded_pdf(data, max_size_mb=max_size_mb)

    # parse_paper 函数，解析 PDF 并经 adapter 转为结构化 ParsedPaper。
    def parse_paper(self, paper_id: str, pdf_path: str) -> tuple[MineruResult, ParsedPaper]:
        mineru_result = self.mineru_client.parse_pdf(paper_id, pdf_path)
        paper = mineru_output_to_paper(mineru_result.content_list_path, paper_id=paper_id)
        return mineru_result, paper
