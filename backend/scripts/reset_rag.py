# -*- coding: utf-8 -*-
"""重置 RAG 向量库：清空全部知识库集合。

现在有两个知识库（fault_codes / manual_chunks），本脚本会把它们都删掉。
日常重新灌库不用手动跑这个 —— `python ingest.py` 内部会先 drop 再重建（幂等）。

用法（backend 目录、已激活 venv、Milvus 服务在线）：
    python scripts/reset_rag.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.vectordb import COLLECTIONS, drop


def main() -> None:
    for source, coll in COLLECTIONS.items():
        drop(source)
        print(f"已删除集合 {coll}（{source}）")
    print("全部知识库已清空。重新灌库请运行：python ingest.py")


if __name__ == "__main__":
    main()
