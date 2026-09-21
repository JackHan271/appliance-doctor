"""MCP server：以标准 MCP 协议暴露工具集。

运行（stdio 传输，供 Claude Desktop 等 MCP client 连接）：
    python -m app.mcp_server

工具函数体都在 tools/ 下，FastAPI 与 MCP server 复用同一套实现。
"""
from mcp.server.fastmcp import FastMCP

from .tools.fault_code import lookup_fault_code
from .tools.nameplate import read_nameplate
from .tools.safety_manual import search_safety_manual
from .tools.symptom import identify_symptom

mcp = FastMCP("appliance-doctor")


@mcp.tool()
def fault_code(brand: str, category: str, code: str, load_type: str | None = None) -> dict:
    """查询家电故障码含义与安全等级。

    category: refrigerator / washing_machine
    load_type: 仅洗衣机需要，top_load（波轮）/ front_load（滚筒）
    """
    r = lookup_fault_code(brand, category, code, load_type)
    return r or {"found": False}


@mcp.tool()
def nameplate(image_base64: str, media_type: str = "image/jpeg") -> dict:
    """识别照片中家电铭牌的品牌、型号与品类。"""
    return read_nameplate(image_base64, media_type)


@mcp.tool()
def symptom(image_base64: str, media_type: str = "image/jpeg") -> dict:
    """识别照片中的家电故障现象、涉及部件与可能原因。"""
    return identify_symptom(image_base64, media_type)


@mcp.tool()
def safety_manual(query: str, top_k: int = 3) -> list[str]:
    """检索通用家电安全手册中的相关须知。"""
    return search_safety_manual(query, top_k)


if __name__ == "__main__":
    mcp.run()
