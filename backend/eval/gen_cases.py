# -*- coding: utf-8 -*-
"""从故障码表**程序化生成**评估用例。

【为什么这么做（评估集设计，面试可讲）】
评估集要扩大，最大的风险是**标注不可靠**——一个标错的用例会掩盖真实 bug
或制造假警报，比没有用例更糟。所以扩量必须找到"有权威来源的标签"。

`data/fault_codes/*.json` 里每个故障码都带 `level` 字段（来自公开维修资料），
这是现成的 ground truth。于是：

    对 (品牌 × 故障码) 的每个组合生成一条用例，expected_level 直接取表里的 level。

这样带来的性质：
  · **标注零猜测**：标签来自公开维修资料，不是我"觉得"应该是 yellow；
  · **完全可复现**：脚本重跑即得；故障码表更新后用例自动同步；
  · **可盘点**：能算清哪些码还没被覆盖；
  · **不会自我欺骗**：标签**绝不来自模型输出**（那是循环论证）。

【安全边界】
生成器**只做机械扩展**，不发明新的期望值。凡是需要判断力、表里没有答案的场景
（对抗输入、多轮收敛、图片、模糊症状），一律**手工编写 + 人工复核**，
不放进自动生成里——见本文件末尾的说明。

用法：
    python eval/gen_cases.py            # 生成并**原地合并**进 eval/cases.json
    python eval/gen_cases.py --dry-run  # 只打印覆盖统计，不写文件

【与手工集的关系】
全部用例合并在一份 `eval/cases.json` 里，靠 `source` 字段区分：
    hand / generated_from_table / safety
本脚本**只替换 `generated_from_table` 那部分**，手工集与安全集原样保留；写前自动备份。
"""
import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND.parent / "data"
CODES_DIR = DATA_DIR / "fault_codes"
CASES_PATH = Path(__file__).resolve().parent / "cases.json"

# 症状表述模板：模拟用户真实口吻，**不泄露安全等级**
TEMPLATES = [
    "{brand}冰箱显示 {code}",
    "{brand}冰箱屏幕上出现 {code} 代码，是什么问题？",
    "我家{brand}冰箱报了 {code}，需要维修吗",
    "{brand}冰箱报警 {code}，自己能不能处理",
]


# 无意义前缀：从故障码含义里截出来的词如果带这些，去掉后才好匹配
# （如「对应温区温度过高/过低提示」→「对应温区」→ 去掉「对应」得「温区」）
_PREFIX_NOISE = ("对应", "该", "此", "本")

# 同义词表：**故障码表里的写法 ↔ 模型实际常写的说法**
# （实测踩坑：表里写「控制板」，模型写「主控板」；表里「化霜」，模型「除霜」——
#   不做同义展开就会把答对的判成"未命中"。）
_SYNONYMS = {
    "控制板": ["主控板", "主板", "电脑板"],
    "主控板": ["控制板", "主板", "电脑板"],
    "化霜": ["除霜"],
    "除霜": ["化霜"],
    "过零": ["过零检测"],
}


def keywords_from_meaning(meaning: str) -> list[str]:
    """从故障码含义里提取关键词（返回列表，**命中任一即算可定位**）。

    【为什么不能用整句当关键词】早期版本取「冷藏室传感器短路或断路」的前缀
    得到「冷藏室传感器」，但模型常写成「冷藏室**温度**传感器」——子串匹配直接失败，
    把答对的判成"未命中"。**这是尺子刻错，不是模型答错。**

    所以三条策略叠加，尽量不误判：
      1. 取**位置/部件词**（第一个语义分界符之前）：更稳、更短；
      2. 含 "/" 的复合词拆开（「微冻室/冷冻室」→ 微冻室、冷冻室）；
      3. 过长的词再补一个更短的前缀（「冷藏室空气温度」→ 再给「冷藏室」）。
    只做机械截断，不做语义"理解"，避免引入主观判断。
    """
    # 取所有分隔符中**位置最靠前**的那个（早期版本按列表顺序取"第一个命中"，
    # 导致「通讯不合格/化霜传感器故障」截成「通讯不合格」而非「通讯」——
    # 模型写「通讯异常」就匹配不上）。
    cuts = [meaning.find(s) for s in
            ("传感器", "故障", "异常", "不合格", "读写", "短路", "断路", "或", "坏", "，", "。")]
    cuts = [i for i in cuts if i >= 2]
    base = meaning[: min(cuts)] if cuts else (meaning[:4] if len(meaning) >= 2 else meaning)

    out: list[str] = []
    for part in base.split("/"):
        part = part.strip()
        # 去掉无意义前缀（保留至少 2 个字，避免把词削没了）
        for noise in _PREFIX_NOISE:
            if part.startswith(noise) and len(part) > len(noise) + 1:
                part = part[len(noise):]
        if not part:
            continue
        out.append(part)
        if len(part) > 4:                      # 补一个更短的前缀，容忍措辞差异
            out.append(part[:3])
        out.extend(_SYNONYMS.get(part, []))    # 补同义说法，容忍用词差异
    return list(dict.fromkeys(out))


def load_codes() -> list[dict]:
    """读取全部品牌的冰箱故障码。"""
    out = []
    for path in sorted(CODES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        brand = data.get("brand", "")
        cat = (data.get("categories") or {}).get("refrigerator") or {}
        for code in cat.get("codes") or []:
            if not code.get("code") or not code.get("level"):
                continue  # 缺 code 或 level 的条目跳过，不做猜测
            out.append(
                {
                    "brand": brand,
                    "code": code["code"],
                    "meaning": code.get("meaning", ""),
                    "level": code["level"],
                    "source_note": code.get("source", ""),
                }
            )
    return out


def build_cases(codes: list[dict]) -> list[dict]:
    """每个故障码 × 若干表述模板 → 一批用例。"""
    cases = []
    for i, c in enumerate(codes):
        kws = keywords_from_meaning(c["meaning"])
        for j, tmpl in enumerate(TEMPLATES):
            cases.append(
                {
                    "id": f"gen_{i:03d}_{j}",
                    "brand": c["brand"],
                    "category": "refrigerator",
                    "symptom": tmpl.format(brand=c["brand"], code=c["code"]),
                    "fault_code": c["code"],
                    # 期望等级直接取故障码表（权威来源），不做任何人工调整
                    "expected_level": c["level"],
                    "expected_keywords": kws,
                    "reason": f'{c["brand"]} {c["code"]}：{c["meaning"]}（等级来自故障码表）',
                    "source": "generated_from_table",
                    "provenance": c.get("source_note", ""),
                }
            )
    return cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    args = ap.parse_args()

    codes = load_codes()
    cases = build_cases(codes)

    by_level: dict[str, int] = {}
    by_brand: dict[str, int] = {}
    for c in cases:
        by_level[c["expected_level"]] = by_level.get(c["expected_level"], 0) + 1
        by_brand[c["brand"]] = by_brand.get(c["brand"], 0) + 1

    print("=" * 56)
    print("故障码覆盖盘点")
    print("=" * 56)
    print(f"  故障码总数：{len(codes)} 条")
    print(f"  生成用例数：{len(cases)} 条（每码 {len(TEMPLATES)} 种表述）")
    print(f"  按等级：{by_level}")
    print(f"  按品牌：{by_brand}")

    if args.dry_run:
        print("\n（--dry-run，未写文件）")
        return

    # ---- 原地合并：只替换 generated_from_table 那部分，手工集与安全集原样保留 ----
    data = json.loads(CASES_PATH.read_text(encoding="utf-8")) if CASES_PATH.exists() else {"name": "", "cases": []}
    old = data.get("cases", [])
    kept = [c for c in old if c.get("source", "hand") != "generated_from_table"]
    replaced = len(old) - len(kept)

    if CASES_PATH.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        backup = CASES_PATH.with_suffix(f".json.bak_{stamp}")
        shutil.copy(CASES_PATH, backup)
        print(f"\n已备份原文件到 {backup.name}")

    data["cases"] = kept + cases
    data.setdefault("name", "家电故障诊断评估集（合并版）")
    CASES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"合并完成：{CASES_PATH.name}")
    print(f"  保留（手工 + 安全）：{len(kept)} 条")
    print(f"  替换（生成）：{replaced} → {len(cases)} 条")
    print(f"  合计：{len(data['cases'])} 条")


if __name__ == "__main__":
    main()
