# 提供论文导入和状态查询接口。
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_paper_service
from app.api.schemas import PaperImportRequest, PaperImportResponse
from app.ingestion.downloader import PaperSource
from app.services.paper_service import PaperService

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("/import", response_model=PaperImportResponse)
# import_paper 函数，导入外部输入并生成系统内记录。
def import_paper(request: PaperImportRequest, service: PaperService = Depends(get_paper_service)) -> PaperImportResponse:
    result = service.import_paper(PaperSource(local_path=request.local_path, metadata=request.metadata))
    return PaperImportResponse(paper_id=result.paper_id, pdf_path=result.pdf_path, file_hash=result.file_hash)


@router.get("/{paper_id}")
# get_paper_status 函数，获取并返回业务对象或状态。
def get_paper_status(paper_id: str) -> dict[str, str]:
    return {"paper_id": paper_id, "status": "unknown"}
