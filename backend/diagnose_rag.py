# -*- coding: utf-8 -*-
"""逐段排查 RAG 链路（双库版）：向量化 / 各知识库检索 / BM25 / 重排 / 完整 retrieve。

哪一环挂了会直接打印异常和调用栈，一次定位。

用法（backend 目录、venv 已激活、Milvus 在线）：
    python diagnose_rag.py
"""
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")

QUERY = "冷藏室不制冷"


def step(no: str, title: str, fn):
    print(f"\n--- {no} {title} ---")
    try:
        result = fn()
    except Exception as exc:
        print(f"  ✗ 失败：{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None
    if isinstance(result, list):
        print(f"  ✓ 返回 {len(result)} 条")
        for item in result[:4]:
            print(f"      - {str(item)[:78]}")
    else:
        print(f"  ✓ {result}")
    return result


def main() -> None:
    from app.config import settings

    print("=" * 64)
    print("配置检查")
    print("=" * 64)
    print(f"  RAG_MODE     = {settings.rag_mode}   RAG_RECALL_N = {settings.rag_recall_n}")
    print(f"  RERANK       = {settings.rerank_enabled}  ({settings.rerank_model})")
    print(f"  分库权重      = {settings.rag_weights}")
    print(f"  MILVUS_URI   = {settings.milvus_uri}")

    # 1. embedding
    from app.embedding import embed_texts

    vec = step("1", "Embedding（BGE 本地模型）", lambda: embed_texts([QUERY])[0])
    if vec is None:
        return
    print(f"      向量维度 = {len(vec)}")

    # 2. 两个知识库分别做稠密检索
    from app.vectordb import COLLECTIONS, all_texts, health, search

    print("\n--- 2 各知识库状态 ---")
    print("   ", health())

    for source, coll in COLLECTIONS.items():
        step("2", f"稠密检索 · {source}（{coll}）", lambda s=source: search(s, vec, top_k=5))

    # 3. 各库语料条数
    corpus: dict[str, list[str]] = {}
    for source in COLLECTIONS:
        texts = step("3", f"取语料 · {source}", lambda s=source: all_texts(s))
        corpus[source] = texts or []

    # 4. 各库 BM25
    from app.bm25 import BM25

    for source, texts in corpus.items():
        if not texts:
            print(f"\n--- 4 BM25 · {source} ---\n  ⚠ 跳过：语料为空")
            continue

        def _bm(ts=texts):
            bm = BM25(ts)
            return [f"{ts[i][:60]}  (score={s:.2f})" for i, s in bm.search(QUERY, top_k=5)]

        step("4", f"BM25 关键词检索 · {source}（{len(texts)} 条）", _bm)

    # 5. 重排
    from app.rerank import rerank

    step("5", "Cross-Encoder 重排", lambda: rerank(QUERY, ["冰箱不制冷的原因", "E1 传感器故障", "门封条老化"], 2))

    # 6. 完整链路（双库加权融合）—— 对比两种 query 的差别
    from app import observability as obs
    from app.rag import retrieve

    queries = [
        ("只用症状",       "冷藏室不制冷"),
        ("症状+品牌+故障码", "海尔 冷藏室不制冷 E1"),
    ]
    for label, q in queries:
        obs.start_trace()
        out = step("6", f"完整 retrieve() · {label}（query = {q!r}）",
                   lambda qq=q: retrieve(qq, top_k=3))
        trace = obs.finish_trace()
        if trace:
            for sp in trace.get("spans", []):
                if sp.get("name") == "rag.retrieve":
                    print("      融合明细：", sp.get("meta"))

    print("\n" + "=" * 64)
    print("排查完成。哪一步出现 ✗ 或 traceback，就是断点所在。")


if __name__ == "__main__":
    main()
