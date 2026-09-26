# 临时探针：分别用「项目当前配置」和「修正配置」连接 MATLAB MCP server，抓真实报错。
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CMD = r"C:\Users\angry\.matlab\agentic-toolkits\bin\matlab-mcp-server.exe"

ARGS_CURRENT = [
    "--matlab-session-mode=new",
    "--matlab-root=D:/matlab",
    r"--extension-file=C:\Users\angry\.matlab\agentic-toolkits\simulink\tools\tools.json",
]
ARGS_FIXED = [
    "--matlab-session-mode=new",
    r"--matlab-root=Y:\matlab",
]


async def probe(name: str, args: list[str], timeout: float) -> None:
    params = StdioServerParameters(command=CMD, args=args)
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await asyncio.wait_for(s.initialize(), timeout=timeout)
                print(f"[{name}] INIT OK: server={getattr(init.serverInfo, 'name', '?')} "
                      f"v{getattr(init.serverInfo, 'version', '?')} protocol={init.protocolVersion}")
                tools = await asyncio.wait_for(s.list_tools(), timeout=30)
                print(f"[{name}] tools({len(tools.tools)}):", [t.name for t in tools.tools][:12])
    except Exception as e:
        print(f"[{name}] FAIL: {type(e).__name__}: {e}")


async def main() -> None:
    await probe("A-项目当前配置", ARGS_CURRENT, timeout=20)
    await probe("B-修正配置  ", ARGS_FIXED, timeout=45)


asyncio.run(main())
