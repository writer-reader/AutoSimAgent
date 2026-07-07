# 创建 FastAPI 应用、注册路由和异常处理器。
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import papers, tasks, workflow
from app.core.exceptions import ControlAgentError


# lifespan 函数，应用生命周期：关闭时释放 MATLAB MCP 单例。
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.tools.mcp_factory import shutdown_matlab_client
    shutdown_matlab_client()


# create_app 函数，封装该模块的一段可复用业务逻辑。
def create_app() -> FastAPI:
    app = FastAPI(title="control-agent", version="0.1.0", lifespan=lifespan)
    app.include_router(papers.router)
    app.include_router(workflow.router)
    app.include_router(tasks.router)

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
