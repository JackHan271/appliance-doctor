"""把语料 embedding 后写入 Milvus（开发期用 Milvus Lite gRPC server 模式）。

用法：先起 Milvus server，再在 backend 目录跑：
    python ingest.py

当前用 data/fault_codes 生成「临时验证语料」跑通 RAG 全链路；
正式语料为 data/manuals 采集的手册文本（见 docs/05-数据策略.md）。
"""
import json

from app.config import settings
from app.embedding import embed_texts
from app.vectordb import COLLECTION, get_client, insert


def build_seed_chunks() -> list[str]:
    """从故障码表生成临时验证语料（后续替换为手册文本）。"""
    chunks: list[str] = []
    codes_dir = settings.data_dir / "fault_codes"
    for f in sorted(codes_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        brand = data.get("brand", "")
        for cat_name, cat in (data.get("categories") or {}).items():
            cat_cn = "冰箱" if cat_name == "refrigerator" else "洗衣机"
            if cat_name == "washing_machine":
                for lt in ("top_load", "front_load"):
                    for c in cat.get(lt, {}).get("codes", []):
                        chunks.append(
                            f"{brand}{cat_cn} 故障码 {c.get('code')}：{c.get('meaning')}"
                            f"（安全等级：{c.get('level')}）"
                        )
            else:
                for c in cat.get("codes", []):
                    chunks.append(
                        f"{brand}{cat_cn} 故障码 {c.get('code')}：{c.get('meaning')}"
                        f"（安全等级：{c.get('level')}）"
                    )
    return chunks


def main() -> None:
    chunks = build_seed_chunks()
    print(f"待入库语料：{len(chunks)} 条")

    # 幂等：清掉旧 collection 重建，避免重复累积
    client = get_client()
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
        print("已清除旧 collection")

    vectors = embed_texts(chunks)
    insert(list(range(len(chunks))), vectors, chunks)
    print(f"入库完成：{len(chunks)} 条")


if __name__ == "__main__":
    main()
