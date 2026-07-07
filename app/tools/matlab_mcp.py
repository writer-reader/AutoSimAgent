# 封装真实 MATLAB MCP 工具（工具名对齐 matlab-mcp-server）。
from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.mcp_client_base import McpClientBase, ToolResult


@dataclass
# MatlabRunResult 类，封装 MATLAB 执行结果。
class MatlabRunResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    artifacts: list[str] = field(default_factory=list)


# _text_of 函数，从 ToolResult 提取可读文本输出。
def _text_of(result: ToolResult) -> str:
    if result.error:
        return result.error
    out = result.output
    return out.get("text") or out.get("result") or str(out)


# MatlabMcpClient 类，MATLAB MCP 业务接口。
class MatlabMcpClient:
    # __init__ 方法，注入底层 MCP 客户端。
    def __init__(self, client: McpClientBase) -> None:
        self.client = client

    # evaluate_code 函数，执行 MATLAB 代码字符串（真实工具 evaluate_matlab_code）。
    def evaluate_code(self, code: str, project_path: str | None = None) -> MatlabRunResult:
        args: dict[str, object] = {"code": code}
        if project_path:
            args["project_path"] = project_path
        result = self.client.call_tool("evaluate_matlab_code", args)
        text = _text_of(result)
        return MatlabRunResult(ok=result.ok, stdout=text if result.ok else "", stderr="" if result.ok else text)

    # run_file 函数，执行 MATLAB 脚本文件（真实工具 run_matlab_file）。
    def run_file(self, script_path: str) -> MatlabRunResult:
        result = self.client.call_tool("run_matlab_file", {"script_path": script_path})
        text = _text_of(result)
        return MatlabRunResult(ok=result.ok, stdout=text if result.ok else "", stderr="" if result.ok else text)

    # run_test_file 函数，运行 MATLAB 单元测试文件（真实工具 run_matlab_test_file）。
    def run_test_file(self, script_path: str) -> ToolResult:
        return self.client.call_tool("run_matlab_test_file", {"script_path": script_path})

    # check_code 函数，静态检查 MATLAB 脚本（真实工具 check_matlab_code）。
    def check_code(self, script_path: str) -> ToolResult:
        return self.client.call_tool("check_matlab_code", {"script_path": script_path})

    # detect_toolboxes 函数，查询已安装 MATLAB 工具箱（真实工具 detect_matlab_toolboxes）。
    def detect_toolboxes(self) -> ToolResult:
        return self.client.call_tool("detect_matlab_toolboxes", {})
