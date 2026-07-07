# 后端服务启动入口。运行后会启动 FastAPI，并加载 app.api.main:app。
from __future__ import annotations

import os

import uvicorn


# main 函数，读取环境变量并启动本地后端服务。
def main() -> None:
    host = os.getenv("CONTROL_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROL_AGENT_PORT", "8000"))
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
