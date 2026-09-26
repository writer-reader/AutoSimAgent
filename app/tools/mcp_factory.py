# MATLAB MCP 客户端工厂：从配置构建进程级单例长连接。
from __future__ import annotations

import threading

from app.core.config_loader import MatlabConfig
from app.graph.router import HIGH_RISK_TOOLS as _DEFAULT_HIGH_RISK
from app.tools.mcp_client_base import StdioMcpClient

_singleton: StdioMcpClient | None = None
_lock = threading.Lock()


# build_matlab_client 函数，按配置构建一个（未启动的）stdio MCP 客户端。
def build_matlab_client(config: MatlabConfig) -> StdioMcpClient:
    if not config.mcp_server_command:
        raise ValueError("matlab.mcp_server_command is empty")
    return StdioMcpClient(
        command=config.mcp_server_command[0],
        args=list(config.mcp_server_command[1:]) + list(config.mcp_server_args),
        startup_timeout_s=config.startup_timeout_s,
        tool_timeout_s=config.tool_timeout_s,
    )


# get_matlab_client 函数，获取进程级单例（首次调用会 start，MATLAB 启动较慢）。
def get_matlab_client(config: MatlabConfig, autostart: bool = True) -> StdioMcpClient:
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = build_matlab_client(config)
            if autostart:
                _singleton.start()
        return _singleton


# shutdown_matlab_client 函数，关闭单例（app 关闭时调用）。
def shutdown_matlab_client() -> None:
    global _singleton
    with _lock:
        if _singleton is not None:
            _singleton.stop()
            _singleton = None


# matlab_client_status 函数，读取单例连接状态（不创建、不启动客户端，无副作用；供 /system/status）。
def matlab_client_status() -> dict:
    with _lock:
        s = _singleton
    if s is None:
        return {"initialized": False, "started": False, "session_alive": False, "loop_alive": False}
    return {"initialized": True, **s.connection_status()}


# is_high_risk 函数，判断工具是否需要人工审批。
def is_high_risk(tool_name: str, config: MatlabConfig | None = None) -> bool:
    risk = set(config.high_risk_tools) if config and config.high_risk_tools else _DEFAULT_HIGH_RISK
    return tool_name in risk
