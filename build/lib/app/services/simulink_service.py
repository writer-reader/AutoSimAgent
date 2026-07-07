# 编排 Simulink 模型构建和仿真调用。
from __future__ import annotations

from typing import Any

from app.tools.mcp_client_base import ToolResult
from app.tools.simulink_toolkit import SimulinkToolkitClient


# SimulinkService 类，封装该模块中的相关状态与行为。
class SimulinkService:
    # __init__ 方法，注入 Simulink MCP 客户端。
    def __init__(self, client: SimulinkToolkitClient) -> None:
        self.client = client

    # read_structure 函数，读取模型结构。
    def read_structure(self, model: str, scope: str = "root") -> ToolResult:
        return self.client.read_model(model, scope=scope)

    # apply_edits 函数，对模型批量应用结构编辑操作。
    def apply_edits(self, model: str, operations: list[dict[str, Any]], scope: str = "root",
                    layout_mode: str = "incremental") -> ToolResult:
        return self.client.edit(model, scope=scope, operations=operations, layout_mode=layout_mode)

    # validate 函数，结构校验模型。
    def validate(self, model: str, scope: str = "root") -> ToolResult:
        return self.client.check(model, scope=scope)

    # run_test 函数，用 Gherkin 规格运行模型测试。
    def run_test(self, model: str, gherkin_file: str, scenarios: list[str] | None = None) -> ToolResult:
        return self.client.run_test(model, gherkin_file, scenarios=scenarios)
