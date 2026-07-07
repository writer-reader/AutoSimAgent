# 真实 stdio MCP 客户端：以专用线程 + 常驻事件循环桥接 async MCP SDK 到同步业务层。
# 进程级单例长连接（MATLAB 启动慢，禁止每次重连）。支持注入 fake session 便于离线测试。
from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.exceptions import ToolExecutionError

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from contextlib import AsyncExitStack
except ImportError:  # pragma: no cover
    ClientSession = None  # type: ignore[assignment]


@dataclass
# ToolSpec 类，封装该模块中的相关状态与行为。
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
# ToolResult 类，工具调用统一结果。
class ToolResult:
    name: str
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# McpClientBase 类，定义 MCP 客户端接口（可被真实/伪实现继承）。
class McpClientBase:
    # start 函数，建立连接。
    def start(self) -> None:
        raise NotImplementedError

    # stop 函数，断开连接。
    def stop(self) -> None:
        raise NotImplementedError

    # list_tools 函数，列出可用工具。
    def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError

    # call_tool 函数，调用工具并返回统一结果。
    def call_tool(self, name: str, arguments: dict[str, Any], timeout_s: int | None = None) -> ToolResult:
        raise NotImplementedError


# StdioMcpClient 类，通过 stdio 连接真实 MCP server 的同步客户端。
class StdioMcpClient(McpClientBase):
    # __init__ 方法，配置启动命令；session_factory 用于注入测试会话。
    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        startup_timeout_s: int = 120,
        tool_timeout_s: int = 300,
        session_factory: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.startup_timeout_s = startup_timeout_s
        self.tool_timeout_s = tool_timeout_s
        self._session_factory = session_factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: Any | None = None
        self._exit_stack: Any | None = None
        self._started = False

    # _run 函数，把协程提交到常驻事件循环并同步等待结果。
    def _run(self, coro: Awaitable[Any], timeout_s: float | None = None) -> Any:
        if self._loop is None:
            raise ToolExecutionError("mcp_not_started", "MCP client is not started", {})
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout_s)

    # start 函数，启动线程/事件循环并建立 MCP 会话。
    def start(self) -> None:
        if self._started:
            return
        ready = threading.Event()
        error_holder: dict[str, BaseException] = {}

        def _thread_main() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_thread_main, name="mcp-client", daemon=True)
        self._thread.start()
        ready.wait(timeout=10)

        async def _connect() -> None:
            if self._session_factory is not None:  # 测试注入路径
                self._session = await self._session_factory()
                return
            if ClientSession is None:
                raise ToolExecutionError("mcp_sdk_missing", "mcp package is not installed", {})
            self._exit_stack = AsyncExitStack()
            params = StdioServerParameters(command=self.command, args=self.args)
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session = session

        try:
            self._run(_connect(), timeout_s=self.startup_timeout_s)
        except BaseException as exc:  # 启动失败：清理线程
            error_holder["e"] = exc
            self.stop()
            raise ToolExecutionError("mcp_start_failed", "Failed to start MCP session", {"error": str(exc)}) from exc
        self._started = True

    # call_tool 函数，调用 MCP 工具并归一化结果。
    def call_tool(self, name: str, arguments: dict[str, Any], timeout_s: int | None = None) -> ToolResult:
        if not self._started or self._session is None:
            raise ToolExecutionError("mcp_not_started", "MCP client is not started", {})
        timeout = timeout_s or self.tool_timeout_s
        try:
            raw = self._run(self._session.call_tool(name, arguments), timeout_s=timeout)
        except Exception as exc:
            return ToolResult(name=name, ok=False, error=str(exc))
        return _normalize_result(name, raw)

    # list_tools 函数，列出 server 暴露的工具。
    def list_tools(self) -> list[ToolSpec]:
        if not self._started or self._session is None:
            raise ToolExecutionError("mcp_not_started", "MCP client is not started", {})
        raw = self._run(self._session.list_tools(), timeout_s=self.tool_timeout_s)
        tools = getattr(raw, "tools", raw) or []
        specs: list[ToolSpec] = []
        for t in tools:
            specs.append(ToolSpec(
                name=getattr(t, "name", ""),
                description=getattr(t, "description", "") or "",
                input_schema=getattr(t, "inputSchema", {}) or {},
            ))
        return specs

    # stop 函数，关闭会话与事件循环。
    def stop(self) -> None:
        if self._loop is not None:
            async def _cleanup() -> None:
                if self._exit_stack is not None:
                    await self._exit_stack.aclose()
            try:
                if self._exit_stack is not None:
                    fut = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
                    fut.result(timeout=30)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._loop = None
        self._thread = None
        self._session = None
        self._exit_stack = None
        self._started = False


# _normalize_result 函数，将 MCP CallToolResult 归一化为 ToolResult。
def _normalize_result(name: str, raw: Any) -> ToolResult:
    is_error = bool(getattr(raw, "isError", False))
    # 优先结构化内容
    structured = getattr(raw, "structuredContent", None)
    if structured is not None:
        return ToolResult(name=name, ok=not is_error, output=_as_dict(structured),
                          error=None if not is_error else _as_text(raw))
    text = _as_text(raw)
    output: dict[str, Any]
    try:
        parsed = json.loads(text)
        output = parsed if isinstance(parsed, dict) else {"result": parsed}
    except (json.JSONDecodeError, ValueError):
        output = {"text": text}
    return ToolResult(name=name, ok=not is_error, output=output, error=text if is_error else None)


# _as_text 函数，从 MCP 内容块提取拼接文本。
def _as_text(raw: Any) -> str:
    content = getattr(raw, "content", None)
    if content is None:
        return str(raw)
    parts: list[str] = []
    for item in content:
        t = getattr(item, "text", None)
        if t is not None:
            parts.append(t)
    return "\n".join(parts) if parts else ""


# _as_dict 函数，尽力将结构化内容转为 dict。
def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"result": value}
