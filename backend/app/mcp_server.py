# -*- coding: utf-8 -*-
"""MCP server：以标准 MCP 协议暴露工具、资源与提示模板。

【MCP 的三种能力都实现了（设计要点）】
规范里 MCP Server 可以暴露三类东西，控制方各不相同：
  · **Tools（工具）**：可执行的函数，**模型自主决定**是否调用（model-controlled）；
  · **Resources（资源）**：可读取的数据源，**由宿主决定**何时纳入上下文（application-driven）；
  · **Prompts（提示模板）**：预定义的提示词，**由用户显式选用**（user-controlled）。

很多项目只实现 Tools 就说"我做了 MCP"，其实只做了三分之一。
这里三种都做了，正好能讲清"工具 / 资源 / 提示模板"的分工。

【传输方式】
默认 stdio（本地子进程，零网络开销）；
加 `--http` 切换为 Streamable HTTP（远程、多客户端、可水平扩展）。

运行：
    python -m app.mcp_server            # stdio（供 Claude Desktop / Cursor 连接）
    python -m app.mcp_server --http     # Streamable HTTP
"""
import json
import sys

from mcp.server.fastmcp import FastMCP

from .config import settings
from .tools.fault_code import lookup_fault_code
from .tools.nameplate import read_nameplate
from .tools.safety_manual import search_safety_manual
from .tools.symptom import identify_symptom

mcp = FastMCP("appliance-doctor")


# ================================================================ Tools
# 可执行的函数，由模型自主决定何时调用。


@mcp.tool()
def fault_code(brand: str, category: str, code: str, load_type: str | None = None) -> dict:
    """查询家电故障码含义与安全等级。

    category: refrigerator（本项目仅支持冰箱）
    load_type: 历史遗留参数（洗衣机波轮/滚筒），冰箱忽略；保留以兼容旧客户端
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


# ================================================================ Resources
# 只读数据源，由宿主（应用）决定何时读取并放进上下文，模型不能自行触发。


def _find_brand_file(brand: str):
    """按中文名或英文名定位品牌故障码文件。"""
    codes_dir = settings.data_dir / "fault_codes"
    for path in sorted(codes_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if brand in (data.get("brand"), data.get("brand_en"), path.stem):
            return data
    return None


@mcp.resource("fault-codes://{brand}/{category}")
def fault_code_table(brand: str, category: str) -> str:
    """读取某品牌某品类的**完整故障码表**（只读资源）。

    与 `fault_code` 工具的区别：工具是"查一条"，资源是"拿整张表"——
    适合宿主想一次性把全表放进上下文做对照的场景。
    """
    data = _find_brand_file(brand)
    if not data:
        return f"未找到品牌「{brand}」的故障码表。可用品牌：海尔 / 美的 / 西门子"
    cat = (data.get("categories") or {}).get(category)
    if not cat:
        return f"品牌「{brand}」下没有分类「{category}」。"
    codes = cat.get("codes") or []
    lines = [f"# {data.get('brand')} · {category} 故障码表（共 {len(codes)} 条）"]
    for c in codes:
        lines.append(f"- {c.get('code')}：{c.get('meaning')}（安全等级 {c.get('level')}）")
    note = data.get("note")
    if note:
        lines.append(f"\n> 说明：{note}")
    return "\n".join(lines)


@mcp.resource("stats://knowledge-base")
def knowledge_base_stats() -> str:
    """知识库统计：各向量库的条数与连通性（只读资源）。"""
    from .vectordb import health

    return json.dumps(health(), ensure_ascii=False, indent=2)


@mcp.resource("safety://levels")
def safety_levels() -> str:
    """三级安全护栏的定义（只读资源，供宿主注入上下文统一口径）。"""
    return (
        "# 家电维修三级安全护栏\n"
        "- green（绿）：完全不打开盖板/面板的表面操作（擦门封、调温度、复位、断电化霜），可安全自修。\n"
        "- yellow（黄）：需打开盖板或接触内部部件（清理排水孔、拆面板清洁），**必须先断电**。\n"
        "- red（红）：涉及高压电、压缩机、制冷剂、主控板、传感器、加热管，"
        "只解释可能原因，**绝不提供自行拆机步骤**，建议联系官方售后。\n"
    )


# ================================================================ Prompts
# 预定义提示模板，由用户显式选用（不是模型自动触发）。


@mcp.prompt()
def diagnose_refrigerator(symptom: str, brand: str = "海尔", fault_code: str = "") -> str:
    """生成一段冰箱故障诊断的提示词（用户可选用，把结构化信息交给模型）。"""
    parts = [
        "你是资深家电维修诊断专家，服务对象是普通家庭用户。",
        f"【品牌】{brand}",
        f"【症状】{symptom}",
    ]
    if fault_code:
        parts.append(f"【故障码】{fault_code}")
    parts.append(
        "请先判断信息是否足够定位问题；不足则只提一个用户能直接回答的追问，"
        "足够则给出诊断结论并标注安全等级（green / yellow / red）。"
    )
    return "\n".join(parts)


@mcp.prompt()
def safety_triage(diagnosis: str) -> str:
    """生成一段"安全等级复核"提示词，用于独立复核某个诊断结论的危险程度。"""
    return (
        "你是家电维修安全审查员，独立复核下面的诊断结论，不受其结论影响。\n"
        f"【诊断结论】{diagnosis}\n"
        "按三级护栏判定安全等级（green / yellow / red），"
        "只要涉及高压电、压缩机、制冷剂、主控板、传感器、加热管一律判 red；"
        "需要打开盖板或接触内部部件至少判 yellow 并补充断电警示。"
    )


# ================================================================ 启动
if __name__ == "__main__":
    if "--http" in sys.argv:
        # Streamable HTTP：远程、多客户端、可水平扩展
        mcp.run(transport="streamable-http")
    else:
        # stdio：本地子进程，零网络开销
        mcp.run()
