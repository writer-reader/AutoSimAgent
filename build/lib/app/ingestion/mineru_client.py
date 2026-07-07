# 封装 MinerU 云 API v4 解析流程：请求上传链接 → 上传 PDF → 轮询任务 → 下载解压产物。
# 产物包含 full.md / content_list.json / images/，其中 content_list.json 交由 adapter 转 ParsedPaper。
from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config_loader import MineruConfig, require_env
from app.core.exceptions import ParseError

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

DEFAULT_BASE_URL = "https://mineru.net"


@dataclass
# MineruResult 类，封装该模块中的相关状态与行为。
class MineruResult:
    paper_id: str
    markdown_path: str
    content_list_path: str
    images_dir: str
    status: str = "parsed"


# MineruClient 类，MinerU 云 API 客户端。
class MineruClient:
    # __init__ 方法，初始化实例依赖和默认参数。
    def __init__(
        self,
        config: MineruConfig | None = None,
        api_key: str | None = None,
        output_root: str | Path = "data/mineru",
        http: Any | None = None,
    ) -> None:
        self.config = config
        self.base_url = (config.api_base_url if config and config.api_base_url else DEFAULT_BASE_URL).rstrip("/")
        self.api_key_env = (config.api_key_env if config and config.api_key_env else "MINERU_API_KEY")
        self._api_key = api_key
        self.timeout_s = config.timeout_s if config else 600
        self.poll_interval_s = config.poll_interval_s if config else 5
        self.model_version = getattr(config, "model_version", None) if config else None
        self.enable_formula = getattr(config, "enable_formula", True) if config else True
        self.enable_table = getattr(config, "enable_table", True) if config else True
        self.output_root = Path(output_root)
        self._http = http

    # _key 函数，取 API 密钥（缺失即 fail-fast）。
    def _key(self) -> str:
        return self._api_key or require_env(self.api_key_env)

    # _client 函数，构造/复用 HTTP 客户端。
    def _client(self) -> Any:
        if self._http is not None:
            return self._http
        if httpx is None:
            raise ParseError("mineru_httpx_missing", "httpx package is not installed", {})
        return httpx.Client(timeout=self.timeout_s)

    # _headers 函数，鉴权头。
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}

    # parse_pdf 函数，完整解析一个本地 PDF，返回落盘后的产物路径。
    def parse_pdf(self, paper_id: str, pdf_path: str) -> MineruResult:
        source = Path(pdf_path)
        if not source.exists():
            raise ParseError("mineru_source_missing", "PDF source for MinerU does not exist", {"paper_id": paper_id})

        client = self._client()
        batch_id, upload_url = self._request_upload_url(client, paper_id, source.name)
        self._upload_file(client, upload_url, source)
        zip_url = self._poll_until_done(client, batch_id, paper_id)
        return self._download_and_extract(client, zip_url, paper_id)

    # _request_upload_url 函数，申请批量上传链接并返回 (batch_id, upload_url)。
    def _request_upload_url(self, client: Any, paper_id: str, file_name: str) -> tuple[str, str]:
        body: dict[str, Any] = {
            "enable_formula": self.enable_formula,
            "enable_table": self.enable_table,
            "files": [{"name": file_name, "data_id": paper_id}],
        }
        if self.model_version:
            body["model_version"] = self.model_version
        resp = client.post(f"{self.base_url}/api/v4/file-urls/batch", headers=self._headers(), json=body)
        data = self._unwrap(resp, "mineru_upload_url_failed")
        urls = data.get("file_urls") or []
        if not data.get("batch_id") or not urls:
            raise ParseError("mineru_upload_url_failed", "MinerU did not return upload URL", {"paper_id": paper_id})
        return data["batch_id"], urls[0]

    # _upload_file 函数，将 PDF 内容 PUT 到预签名链接。
    def _upload_file(self, client: Any, upload_url: str, source: Path) -> None:
        content = source.read_bytes()
        resp = client.put(upload_url, content=content)
        if getattr(resp, "status_code", 200) >= 300:
            raise ParseError("mineru_upload_failed", "Uploading PDF to MinerU failed", {"status": resp.status_code})

    # _poll_until_done 函数，轮询批任务直到完成，返回结果 zip 链接。
    def _poll_until_done(self, client: Any, batch_id: str, paper_id: str) -> str:
        deadline = time.monotonic() + self.timeout_s
        url = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        while time.monotonic() < deadline:
            resp = client.get(url, headers=self._headers())
            data = self._unwrap(resp, "mineru_poll_failed")
            for entry in data.get("extract_result", []):
                if entry.get("data_id") not in (paper_id, None) and len(data.get("extract_result", [])) > 1:
                    continue
                state = entry.get("state")
                if state == "done":
                    zip_url = entry.get("full_zip_url")
                    if not zip_url:
                        raise ParseError("mineru_no_result", "MinerU done but no result URL", {"paper_id": paper_id})
                    return zip_url
                if state in ("failed", "error"):
                    raise ParseError("mineru_task_failed", entry.get("err_msg", "MinerU task failed"), {"paper_id": paper_id})
            time.sleep(self.poll_interval_s)
        raise ParseError("mineru_timeout", "MinerU parsing timed out", {"paper_id": paper_id, "timeout_s": self.timeout_s})

    # _download_and_extract 函数，下载结果 zip 并解压，定位 markdown/content_list/images。
    def _download_and_extract(self, client: Any, zip_url: str, paper_id: str) -> MineruResult:
        resp = client.get(zip_url)
        if getattr(resp, "status_code", 200) >= 300:
            raise ParseError("mineru_download_failed", "Downloading MinerU result failed", {"status": resp.status_code})
        out_dir = self.output_root / paper_id
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(out_dir)

        content_list = self._find(out_dir, "content_list.json")
        if content_list is None:
            raise ParseError("mineru_no_content_list", "content_list.json missing in result", {"paper_id": paper_id})
        markdown = self._find(out_dir, "full.md") or self._find_suffix(out_dir, ".md")
        images_dir = out_dir / "images"
        return MineruResult(
            paper_id=paper_id,
            markdown_path=str(markdown) if markdown else "",
            content_list_path=str(content_list),
            images_dir=str(images_dir),
        )

    # _unwrap 函数，校验并解包 MinerU 统一响应体 {code,data,msg}。
    @staticmethod
    def _unwrap(resp: Any, error_code: str) -> dict[str, Any]:
        if getattr(resp, "status_code", 200) >= 300:
            raise ParseError(error_code, "MinerU API returned HTTP error", {"status": resp.status_code})
        payload = resp.json()
        if payload.get("code") not in (0, "0", None):
            raise ParseError(error_code, payload.get("msg", "MinerU API error"), {"code": payload.get("code")})
        return payload.get("data") or {}

    # _find 函数，在目录树中按文件名后缀查找首个匹配文件。
    @staticmethod
    def _find(root: Path, name_suffix: str) -> Path | None:
        for p in root.rglob("*"):
            if p.is_file() and p.name.endswith(name_suffix):
                return p
        return None

    # _find_suffix 函数，在目录树中查找首个指定扩展名文件。
    @staticmethod
    def _find_suffix(root: Path, ext: str) -> Path | None:
        for p in root.rglob(f"*{ext}"):
            if p.is_file():
                return p
        return None
