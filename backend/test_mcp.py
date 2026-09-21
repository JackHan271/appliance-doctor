"""MCP server 验证脚本：连接 stdio server，列出工具并调用 fault_code 工具。

用法（在 backend 目录、已激活 venv）：
    python test_mcp.py

预期：列出 4 个工具（fault_code / nameplate / symptom / safety_manual），
并返回海尔洗衣机 E1（波轮）的查表结果。
"""
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(command="python", args=["-m", "app.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("=== 工具列表 ===")
            for t in tools.tools:
                print(f"- {t.name}: {t.description}")

            print("\n=== 调用 fault_code ===")
            result = await session.call_tool(
                "fault_code",
                {
                    "brand": "海尔",
                    "category": "washing_machine",
                    "code": "E1",
                    "load_type": "top_load",
                },
            )
            for c in result.content:
                if getattr(c, "text", None):
                    print(c.text)


if __name__ == "__main__":
    asyncio.run(main())
