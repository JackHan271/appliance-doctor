# -*- coding: utf-8 -*-
"""统一语料入库：**分两个知识库**写入。

    fault_codes   ← 故障码知识（结构化、高置信）
    manual_chunks ← 中文手册文本（非结构化、补充）

用法（backend 目录、已激活 venv、Milvus 服务在线）：
    python ingest.py                # 全部：故障码 + 手册
    python ingest.py --no-manuals   # 只入故障码（快，适合验证链路）

设计要点（面试可讲）：
1. 【故障码与手册分库】两类知识异构，混在一个 collection 里会互相竞争：
   实测 23 条故障码被 85 条手册完全淹没（手册片段更长、查询词重复更多）。
   分库后检索时按权重融合，从根上避免"数量多的压过权威度高的"。
2. 【剔除非中文语料】采集到的手册里有德语（海外型号）。
   中文 query 检索德语文本 = 纯噪声。用「中文字符占比」过滤，零依赖。
3. 【故障码扩写成自然语句】把 level 展开成安全说明，
   让片段本身可读、可被重排模型理解，也让证据核验有据可依。
4. 【幂等】每次 drop 后重建，避免像旧脚本那样反复运行导致语料重复累积
   （旧脚本用 init_collection 只建不删，跑 4 次就存了 4 份重复片段）。
"""
import argparse
import json
import re
import sys

from app.config import settings
from app.embedding import embed_texts
from app.vectordb import drop, insert

# ---------------- 切分与过滤参数 ----------------
CHUNK_SIZE = 500          # 手册片段目标长度（字符）
OVERLAP = 50              # 相邻片段重叠
MIN_CHUNK = 30            # 过短片段丢弃
MIN_CJK_RATIO = 0.25      # 中文字符占比低于此值 → 判为非中文，丢弃
CJK_RE = re.compile(r"[一-鿿]")

# 安全等级 → 自然语言说明（写进语料，提升检索命中与证据可读性）
LEVEL_DESC = {
    "green": "安全等级 green：属表面操作（擦拭、调温、复位等），可安全自修。",
    "yellow": "安全等级 yellow：需打开盖板或接触内部部件，务必先断电再操作。",
    "red": "安全等级 red：涉及高压电 / 压缩机 / 制冷剂 / 主控板 / 传感器，"
           "必须联系官方售后，不提供自行拆机维修步骤。",
}


def cjk_ratio(text: str) -> float:
    """中文字符占比。用于判断片段是否为中文。"""
    if not text:
        return 0.0
    return len(CJK_RE.findall(text)) / len(text)


# ---------------- 语料一：故障码知识 ----------------
def build_fault_code_chunks() -> list[str]:
    """把故障码表扩写成自然语句片段。"""
    chunks: list[str] = []
    codes_dir = settings.data_dir / "fault_codes"
    for path in sorted(codes_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        brand = data.get("brand", "")
        for cat_name, cat in (data.get("categories") or {}).items():
            cat_cn = {"refrigerator": "冰箱", "washing_machine": "洗衣机"}.get(cat_name, cat_name)

            groups = []
            if cat_name == "washing_machine":
                for lt, lt_cn in (("top_load", "波轮"), ("front_load", "滚筒")):
                    groups.append((f"{lt_cn}式", (cat.get(lt) or {}).get("codes") or []))
            else:
                groups.append(("", cat.get("codes") or []))

            for lt_cn, codes in groups:
                for c in codes:
                    chunks.append(
                        f"{brand}{cat_cn}{lt_cn} 故障码 {c.get('code', '')}：{c.get('meaning', '')}。"
                        f"{LEVEL_DESC.get(c.get('level', ''), '')}"
                    )
    return chunks


# ---------------- 语料二：手册文本（仅中文） ----------------
def extract_pdf_text(pdf_path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def chunk_text(text: str) -> list[str]:
    out = []
    step = CHUNK_SIZE - OVERLAP
    for i in range(0, len(text), step):
        chunk = text[i : i + CHUNK_SIZE].strip()
        if len(chunk) >= MIN_CHUNK:
            out.append(chunk)
    return out


def build_manual_chunks() -> tuple[list[str], dict]:
    """解析 raw/ 下所有 PDF，切分并过滤非中文片段。"""
    raw_dir = settings.data_dir / "manuals" / "raw"
    stats: dict = {"files": [], "skipped_non_cjk": 0}
    kept: list[str] = []

    for pdf in sorted(raw_dir.glob("*.pdf")):
        if pdf.stat().st_size < 100:
            print(f"  跳过 {pdf.name}（文件过小/为空）")
            continue
        try:
            text = extract_pdf_text(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"  跳过 {pdf.name}（解析失败：{exc}）")
            continue

        chunks = chunk_text(text)
        cjk_chunks = [c for c in chunks if cjk_ratio(c) >= MIN_CJK_RATIO]
        dropped = len(chunks) - len(cjk_chunks)
        stats["skipped_non_cjk"] += dropped
        stats["files"].append(
            {"name": pdf.name, "chunks": len(chunks), "kept": len(cjk_chunks), "dropped": dropped}
        )
        kept.extend(cjk_chunks)
    return kept, stats


# ---------------- 入库 ----------------
def write_bank(source: str, chunks: list[str]) -> None:
    """把一批语料写入指定知识库（先 drop 保证幂等）。"""
    print(f"\n[{source}] 待入库 {len(chunks)} 条")
    drop(source)
    vectors = embed_texts(chunks)
    BATCH = 100
    for start in range(0, len(chunks), BATCH):
        end = min(start + BATCH, len(chunks))
        insert(source, list(range(start, end)), vectors[start:end], chunks[start:end])
        print(f"  已入库 {end}/{len(chunks)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-manuals", action="store_true", help="只入故障码，跳过手册")
    args = parser.parse_args()

    print("=" * 56)
    print("构建语料")
    print("=" * 56)

    fault_chunks = build_fault_code_chunks()
    print(f"故障码知识：{len(fault_chunks)} 条")

    manual_chunks: list[str] = []
    if args.no_manuals:
        print("手册文本：已跳过（--no-manuals）")
    else:
        print("手册文本：")
        manual_chunks, stats = build_manual_chunks()
        for f in stats["files"]:
            print(f"  {f['name']}: 切出 {f['chunks']} 段，"
                  f"保留 {f['kept']} 段，丢弃 {f['dropped']} 段（非中文）")
        print(f"  合计保留：{len(manual_chunks)} 条，丢弃非中文：{stats['skipped_non_cjk']} 条")

    if not fault_chunks and not manual_chunks:
        print("没有可入库的语料，退出。")
        sys.exit(1)

    print("\n开始 embedding（首次会加载 BGE 模型，请稍候）...")

    # 故障码库
    if fault_chunks:
        write_bank("fault_code", fault_chunks)

    # 手册库
    if manual_chunks:
        write_bank("manual", manual_chunks)

    print(f"\n✅ 入库完成：故障码 {len(fault_chunks)} 条 + 手册 {len(manual_chunks)} 条")
    print("提示：重新灌库后，正在运行的后端需重启（或调用 /api/admin/reindex）才能刷新关键词索引。")


if __name__ == "__main__":
    main()
