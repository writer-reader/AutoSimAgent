# 请求级访问日志中间件：每个请求一条结构化 JSON 日志（方法/路径/状态/耗时/请求 ID），
# 替代 uvicorn 的文本 access log（在 main.lifespan 里关掉 uvicorn.access，避免双重记录）。
# request_id 同时写入日志上下文，端点内的日志自动携带，可和访问日志按请求串联。
from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.log_context import reset_log_context, set_log_context

logger = logging.getLogger("app.api.access")

# 静默路径：高频轮询（前端每 5s 一次）和健康检查不值得逐条记录（出错仍会记，见下方级别规则——
# 静默路径直接短路，连错误也不经本中间件，由异常处理器/uvicorn.error 兜底）。
DEFAULT_QUIET_PATHS = ("/system/status", "/health")


# AccessLogMiddleware 类，把每个 HTTP 请求折叠成一条带独立字段的 JSON 访问日志。
class AccessLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, quiet_paths: tuple[str, ...] = DEFAULT_QUIET_PATHS) -> None:
        super().__init__(app)
        self.quiet_paths = quiet_paths

    # dispatch 函数，包住下游处理：计时、注入 request_id、按状态码定级输出。
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self.quiet_paths:
            return await call_next(request)

        request_id = uuid4().hex[:12]
        token = set_log_context(request_id=request_id, trace_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            # 异常也会走到这里：记一条 500 再让异常继续向上（ServerErrorMiddleware 兜底成响应）。
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            client = request.client.host if request.client else "-"
            logger.log(
                _level_for(status),
                "%s %s -> %s",
                request.method,
                path,
                status,
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_path": path,
                    "http_status": status,
                    "duration_ms": duration_ms,
                    "client": client,
                },
            )
            reset_log_context(token)


# _level_for 函数，按响应状态码定日志级别：5xx=ERROR，4xx=WARNING，其余 INFO。
def _level_for(status: int) -> int:
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO
