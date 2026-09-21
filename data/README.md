# 数据目录说明（data/）

本目录存放项目的数据产物。按 `docs/05-数据策略.md`，数据与代码分离：本目录数据不入代码仓库、不随代码分发。

## 结构

- `fault_codes/`：品牌故障码表（JSON）
- `models/`：型号种子数据（JSON）
- `manuals/`：手册 RAG 语料（采集脚本 + `raw/` 下载目录）

## 故障码 JSON 结构

字段对齐 `docs/03-设计规范.md` 的 fault_code schema（brand / category / code / meaning / level / source），并扩展顶层 `note` 与 `references`（溯源）。

```json
{
  "brand": "海尔",
  "brand_en": "Haier",
  "note": "含义因型号/系列而异，以具体说明书为准",
  "references": ["https://..."],
  "categories": {
    "refrigerator": { "note": "...", "codes": [ {"code": "E1", "meaning": "...", "level": "red", "source": "..."} ] }
  }
}
```

## 安全等级（level）

- `green`：可安全自修（表面操作，不拆机）
- `yellow`：谨慎操作（打开盖板/接触内部，强制断电 + 警示）
- `red`：必须联系专业师傅（传感器/电路/制冷剂/压缩机/主控板等）

## 品类与品牌范围（MVP）

- 品类：**冰箱**（refrigerator）
- 品牌：**海尔、美的、西门子**（三品牌）
- 数据完整度：故障码为公开资料整理，仅覆盖常见代码，非官方完整表；含义因型号/系列而异，以具体说明书为准。西门子冰箱代码为第三方资料、非官方确认。
