# -*- coding: utf-8 -*-
"""RAG 检索：双库混合检索（稠密 + BM25）+ 加权 RRF + Cross-Encoder 重排。

链路（面试可讲）：

    query
      ├─ 故障码库（结构化、高置信）
      │    ├─ 稠密：embedding → Milvus(fault_codes)
      │    └─ 稀疏：BM25 over 故障码语料
      └─ 手册库（非结构化、补充）
           ├─ 稠密：embedding → Milvus(manual_chunks)
           └─ 稀疏：BM25 over 手册语料
                ↓
        ①每库按配额保底取候选（故障码12席 + 手册8席）
        ②加权 RRF 定序（故障码权重1.5 > 手册1.0）
                ↓
        Cross-Encoder 精排 → Top-K
                ↓
        交给 LLM

【为什么分库 + 配额 + 加权（真实踩坑 + 迭代）】
初版把故障码和手册混在同一个 collection 里检索，实测发现：
**23 条故障码被 85 条手册完全淹没**——手册片段更长、对查询词的重复更多，
稠密和稀疏两路都把手册排在前面。更致命的是，融合后前 20 名全是手册，
送到重排器时**故障码已经被切掉了**，重排器根本看不到它们。

改成双库后先试了纯加权，又发现**矫枉过正**：权重 1.5 时前 20 名全是故障码，
手册一条进不去——那"冰箱有异味怎么办"这类**没有故障码的查询**就会失衡。

最终方案是**配额 + 加权**两条腿：
  · 配额保证两类知识都能进重排器（不被对方挤掉）；
  · 加权让更权威的故障码在定序时靠前。
最终由 Cross-Encoder 按真实相关性裁决——**不靠人工规则决定谁赢**。

【健壮性】任一步失败都优雅降级：
稠密挂→只用稀疏；BM25 不可用→只用稠密；重排挂→用融合顺序。
检索链路不能因为某个可选环节挂掉而整体不可用。
"""
from __future__ import annotations

from . import cache
from .bm25 import BM25, rrf, rrf_weighted
from .config import settings
from .embedding import embed_texts
from .observability import span
from .rerank import rerank
from .vectordb import all_texts, search

# 参与检索的知识源（与 vectordb.COLLECTIONS 对应）
SOURCES = ("fault_code", "manual")

_bm25: dict[str, BM25] = {}
_bm25_tried: set[str] = set()


def _get_bm25(source: str) -> BM25 | None:
    """惰性构建某个知识源的 BM25 索引。每个源只尝试一次，失败不再重试。"""
    if source in _bm25:
        return _bm25[source]
    if source in _bm25_tried:
        return None
    _bm25_tried.add(source)
    try:
        texts = all_texts(source)
        if texts:
            _bm25[source] = BM25(texts)
    except Exception:
        pass
    return _bm25.get(source)


def _recall_one(query: str, source: str, vec, n: int) -> tuple[list[str], list[str]]:
    """对单个知识源做稠密 + 稀疏召回，返回 (dense_texts, sparse_texts)。"""
    dense: list[str] = []
    if vec is not None:
        try:
            for hit in search(source, vec, top_k=n):
                text = (hit.get("entity") or {}).get("text", "")
                if text:
                    dense.append(text)
        except Exception:
            dense = []

    sparse: list[str] = []
    bm = _get_bm25(source)
    if bm is not None:
        sparse = [bm.corpus[i] for i, _ in bm.search(query, top_k=n)]

    return dense, sparse


def retrieve(query: str, top_k: int = 3) -> list[str]:
    """检索入口。返回与 query 最相关的文本片段（可能为空列表）。

    【结果缓存】检索是确定性计算（同样的 query + 同样的语料 → 同样的结果），
    而多轮对话里同一症状会被反复检索，所以按 query 缓存结果收益明显。
    重新灌库后 `reset_indexes()` 会清空缓存，避免用到旧语料的结果。
    """
    if not query:
        return []

    ck = cache.make_generic_key("rag", query, top_k, settings.rag_mode, SOURCES)
    hit = cache.get_json(ck)
    if hit is not None:
        return hit

    n = settings.rag_recall_n
    weights = settings.rag_weights
    quota = settings.rag_quota

    with span("rag.retrieve", "tool", input_preview=query,
              mode=settings.rag_mode, sources="+".join(SOURCES)) as s:
        try:
            vec = embed_texts([query])[0]
        except Exception:
            vec = None  # 稠密路不可用，后面只用稀疏路

        # 1) 每个知识库各自融合（库内：稠密 + 稀疏 → RRF）
        per_source: dict[str, list[str]] = {}
        detail: dict = {}
        for source in SOURCES:
            dense, sparse = _recall_one(query, source, vec, n)
            detail[f"{source}_dense"] = len(dense)
            detail[f"{source}_sparse"] = len(sparse)
            rankings = [r for r in (dense, sparse) if r]
            if len(rankings) > 1:
                per_source[source] = rrf(rankings)
            elif rankings:
                per_source[source] = rankings[0]
            else:
                per_source[source] = []

        # 2) 每库按配额**保底**取候选 —— 保证两类知识都能进重排器
        merged: list[str] = []
        for source in SOURCES:
            cap = int(quota.get(source, 10))
            merged.extend(per_source[source][:cap])

        # 3) 用加权 RRF 给合并候选定序（跨库）：
        #    故障码权威度更高 → 同样进候选时排前面，截断时也优先保留
        cross = rrf_weighted(
            [(per_source[s], float(weights.get(s, 1.0))) for s in SOURCES if per_source[s]]
        )
        rank = {doc: i for i, doc in enumerate(cross)}
        merged = sorted(dict.fromkeys(merged), key=lambda d: rank.get(d, 10 ** 9))

        # 4) Cross-Encoder 精排 —— 最终由它按真实相关性裁决
        candidates = merged[: settings.rerank_candidates]
        out = rerank(query, candidates, top_k) if candidates else []

        detail.update(candidates=len(candidates), returned=len(out))
        s.meta.update(**detail)

    cache.set_json(ck, out)
    return out


def reset_indexes() -> None:
    """清空进程内 BM25 索引与检索缓存（重新灌库后调用，避免继续用旧语料）。"""
    _bm25.clear()
    _bm25_tried.clear()
    cache.invalidate("rag")   # 语料变了，旧的检索结果必须失效
