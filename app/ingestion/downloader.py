# 处理本地 PDF 导入、校验、哈希计算和归档保存。
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.exceptions import DownloadError


@dataclass
# PaperSource 类，封装该模块中的相关状态与行为。
class PaperSource:
    local_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
# DownloadResult 类，封装该模块中的相关状态与行为。
class DownloadResult:
    paper_id: str
    pdf_path: str
    file_hash: str
    metadata: dict[str, Any]


# sha256_file 函数，封装该模块的一段可复用业务逻辑。
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# import_local_pdf 函数，导入外部输入并生成系统内记录。
def import_local_pdf(source: PaperSource, data_dir: str | Path = "data/papers", max_size_mb: int = 100) -> DownloadResult:
    path = Path(source.local_path)
    if not path.exists():
        raise DownloadError("paper_missing", "PDF file does not exist", {"source": path.name})
    if path.suffix.lower() != ".pdf":
        raise DownloadError("paper_not_pdf", "Only PDF files are supported", {"suffix": path.suffix})
    if path.stat().st_size > max_size_mb * 1024 * 1024:
        raise DownloadError("paper_too_large", "PDF file exceeds configured size limit", {"max_size_mb": max_size_mb})

    file_hash = sha256_file(path)
    paper_id = f"paper_{file_hash[:12]}"
    output_dir = Path(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{paper_id}.pdf"
    shutil.copy2(path, output_path)
    return DownloadResult(paper_id=paper_id, pdf_path=str(output_path), file_hash=file_hash, metadata=source.metadata)
