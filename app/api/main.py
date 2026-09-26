# 创建 FastAPI 应用、注册路由和异常处理器。
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.access_log import AccessLogMiddleware
from app.api.routers import papers, system, tasks, workflow
from app.core.exceptions import ControlAgentError

# 事件保留期（天）：启动清理更早的事件，环境变量可覆盖（0 及负数视为不清理）。
_EVENT_RETENTION_DAYS = int(os.environ.get("CONTROL_AGENT_EVENT_RETENTION_DAYS", "30"))


# lifespan 函数，应用生命周期：启动扫描孤儿任务 + 清理过期事件 + 关闭时释放 MATLAB MCP 单例。
@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn 的文本 access log 在 uvicorn 启动时配置（晚于本模块导入），
    # 这里在其之后关闭，访问日志统一由 AccessLogMiddleware 以 JSON 结构化输出。
    logging.getLogger("uvicorn.access").disabled = True
    # 启动扫描：把进程被杀留下的 status=='running' 任务标为 interrupted（可经 /restart 恢复）
    try:
        from app.api.dependencies import get_config
        from app.services.orchestrator_service import registry
        try:
            cfg = get_config()
            registry.reconfigure(cfg.graph.session_db_path)
        except Exception:
            pass  # 配置缺失时用默认库路径扫描
        n = registry.mark_orphans_interrupted()
        if n:
            logging.getLogger(__name__).info("startup orphan scan: %d running tasks -> interrupted", n)
        if _EVENT_RETENTION_DAYS > 0:
            pruned = registry.event_store().prune_events(_EVENT_RETENTION_DAYS)
            if pruned:
                logging.getLogger(__name__).info(
                    "startup event retention: pruned %d events older than %d days", pruned, _EVENT_RETENTION_DAYS
                )
    except Exception:
        pass  # 扫描失败不阻止应用启动
    yield
    from app.tools.mcp_factory import shutdown_matlab_client
    shutdown_matlab_client()


# create_app 函数，封装该模块的一段可复用业务逻辑。
def create_app() -> FastAPI:
    # 用 core.yaml 配置初始化日志（消费之前死配置的 log_level/log_path）
    try:
        from app.api.dependencies import get_config
        from app.core.logging_config import configure_logging
        cfg = get_config()
        configure_logging(cfg.core.log_level, cfg.core.log_path)
    except Exception:
        pass  # 配置加载失败时退回默认 INFO 级别，不阻止应用启动
    app = FastAPI(title="control-agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(AccessLogMiddleware)
    app.include_router(papers.router)
    app.include_router(workflow.router)
    app.include_router(tasks.router)
    app.include_router(system.router)

    @app.exception_handler(ControlAgentError)
    # control_agent_error_handler 函数，封装该模块的一段可复用业务逻辑。
    async def control_agent_error_handler(request: Request, exc: ControlAgentError) -> JSONResponse:
        return JSONResponse(status_code=400, content=exc.to_public_dict())

    @app.get("/health")
    # health 函数，封装该模块的一段可复用业务逻辑。
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
