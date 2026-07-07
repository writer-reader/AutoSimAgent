# 封装真实 Simulink MCP 工具（以 model_edit 的 operations 数组为核心）。
from __future__ import annotations

import json
from typing import Any

from app.tools.mcp_client_base import McpClientBase, ToolResult


# SimulinkToolkitClient 类，Simulink MCP 业务接口。
class SimulinkToolkitClient:
    # __init__ 方法，注入底层 MCP 客户端。
    def __init__(self, client: McpClientBase) -> None:
        self.client = client

    # read_model 函数，读取模型结构与算法（真实工具 model_read）。
    def read_model(self, model: str, scope: str = "root", depth: str = "inf") -> ToolResult:
        return self.client.call_tool("model_read", {"model": model, "scope": scope, "depth": depth})

    # overview 函数，读取模型层级总览（真实工具 model_overview）。
    def overview(self, model: str, scope: str = "root", detail: str = "full") -> ToolResult:
        return self.client.call_tool("model_overview", {"model": model, "scope": scope, "detail": detail})

    # edit 函数，批量结构编辑：operations 为操作数组（真实工具 model_edit，🔴高风险）。
    def edit(self, model: str, scope: str, operations: list[dict[str, Any]], layout_mode: str = "incremental") -> ToolResult:
        return self.client.call_tool("model_edit", {
            "model": model, "scope": scope,
            "operations": json.dumps(operations, ensure_ascii=False),
            "layout_mode": layout_mode,
        })

    # check 函数，结构校验（真实工具 model_check）。
    def check(self, model: str, scope: str = "root", checks: list[str] | None = None) -> ToolResult:
        return self.client.call_tool("model_check", {
            "model": model, "scope": scope,
            "checks": json.dumps(checks or ["all"]),
        })

    # query_params 函数，查询块/信号/配置参数（真实工具 model_query_params）。
    def query_params(self, model: str, targets: list[str], params: list[str], compile: bool = False) -> ToolResult:
        return self.client.call_tool("model_query_params", {
            "model": model,
            "targets": json.dumps(targets),
            "params": json.dumps(params),
            "compile": "true" if compile else "false",
        })

    # run_test 函数，用 Gherkin 规格执行模型测试（真实工具 model_test，🔴高风险）。
    def run_test(self, model: str, gherkin_file: str, scenarios: list[str] | None = None) -> ToolResult:
        return self.client.call_tool("model_test", {
            "model": model, "gherkin_file": gherkin_file,
            "scenarios": json.dumps(scenarios or []),
            "verbose": "false", "draft_mode": "false", "coverage": "none",
        })
