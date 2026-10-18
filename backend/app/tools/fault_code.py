"""查故障码工具（后续以 MCP server 形式暴露，此处为函数体）。"""
import json

from ..config import settings

BRANDS = {"海尔": "haier", "美的": "midea", "西门子": "siemens"}


def _load(brand_en: str) -> dict:
    path = settings.data_dir / "fault_codes" / f"{brand_en}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lookup_fault_code(
    brand: str,
    category: str,
    code: str,
    load_type: str | None = None,
) -> dict | None:
    """按品牌 + 品类 + 故障码查询。

    category: refrigerator（冰箱）/ air_conditioner（空调）
    load_type: 已废弃参数（早期洗衣机维度），保留仅为兼容旧调用；冰箱项目忽略。
    """
    brand_en = BRANDS.get(brand)
    if not brand_en:
        return None
    data = _load(brand_en)
    cat = data["categories"].get(category)
    if not cat:
        return None

    codes = cat.get("codes", [])

    for c in codes:
        candidates = [part.strip().upper() for part in c["code"].split("/")]
        if code.upper() in candidates:
            return {"brand": brand, "category": category, **c}
    return None
