"""重置 RAG 向量库：清空 manual_chunks 集合（删除之前入库的洗衣机语料）。

用法（backend 目录、已激活 venv、Milvus 服务在线）：
    python scripts/reset_rag.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.vectordb import COLLECTION, get_client


def main() -> None:
    client = get_client()
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
        print(f"已删除集合 {COLLECTION}（旧的洗衣机语料已清空）")
    else:
        print(f"集合 {COLLECTION} 不存在，无需删除")


if __name__ == "__main__":
    main()
