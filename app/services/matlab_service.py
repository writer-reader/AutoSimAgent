# 编排 MATLAB 代码执行结果的基础校验。
from __future__ import annotations

from dataclasses import dataclass

from app.tools.matlab_mcp import MatlabMcpClient, MatlabRunResult


@dataclass
# MatlabValidationResult 类，封装该模块中的相关状态与行为。
class MatlabValidationResult:
    ok: bool
    run_result: MatlabRunResult
    warnings: list[str]


# MatlabService 类，封装该模块中的相关状态与行为。
class MatlabService:
    # __init__ 方法，注入 MATLAB MCP 客户端。
    def __init__(self, client: MatlabMcpClient) -> None:
        self.client = client

    # execute_code 函数，执行 MATLAB 代码并做基础校验。
    def execute_code(self, code: str, project_path: str | None = None) -> MatlabValidationResult:
        result = self.client.evaluate_code(code, project_path=project_path)
        warnings: list[str] = []
        if "NaN" in result.stdout or "Inf" in result.stdout:
            warnings.append("output_contains_nan_or_inf")
        return MatlabValidationResult(ok=result.ok and not warnings, run_result=result, warnings=warnings)

    # run_file 函数，执行 MATLAB 脚本文件。
    def run_file(self, script_path: str) -> MatlabRunResult:
        return self.client.run_file(script_path)
