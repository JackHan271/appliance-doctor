# -*- coding: utf-8 -*-
"""重排序：用 Cross-Encoder 对召回的候选做精排。

为什么需要重排（设计要点）：
向量检索走的是**双塔（Bi-Encoder）**——query 和 doc 各自独立编码、doc 向量可预计算，
所以快；代价是 query 和 doc **从未"见过面"**，只能比一个粗糙的向量相似度，
Top-K 里经常混进"语义相近但答非所问"的噪声，也排不准真正最相关的那个。

Cross-Encoder 把 (query, doc) **拼在一起**送进模型，能建模两者的交互，精度高得多；
但每一对都要跑一次完整推理，**无法预计算**，10 万文档全量精排要 10 万次推理，
算力上不可行。所以只能用在少量候选上：

    第一阶段 Bi-Encoder 粗召回 Top-50~100  →  第二阶段 Cross-Encoder 精排 Top-3~10

这就是工业 RAG 标准的「两阶段检索」。

注意：向量库入库和查询必须用同一个 embedding 模型（否则向量空间不一致），
但**重排模型与 embedding 模型是独立的**，它只吃 (query, doc) 文本对。
"""
from __future__ import annotations

from .config import settings

_reranker = None


def _get_reranker():
    """惰性加载，避免没用到重排时也吃显存/内存。"""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(settings.rerank_model, max_length=settings.rerank_max_length)
    return _reranker


def warmup() -> bool:
    """预热：提前把重排模型加载进内存。

    首次加载 1GB 级的模型要 40 秒上下，如果发生在用户请求里就是"第一枪特别慢"。
    启动时后台预热一次，把这个成本从请求路径上挪走。
    """
    try:
        _get_reranker()
        return True
    except Exception:
        return False


def rerank(query: str, docs: list[str], top_k: int = 3) -> list[str]:
    """对候选文档精排，返回 top_k。任何异常都回退到原顺序，绝不让重排成为故障点。"""
    if not docs:
        return []
    if not settings.rerank_enabled or len(docs) == 1:
        return docs[:top_k]
    try:
        model = _get_reranker()
        scores = model.predict([(query, d) for d in docs])
        order = sorted(range(len(docs)), key=lambda i: float(scores[i]), reverse=True)
        return [docs[i] for i in order[:top_k]]
    except Exception:
        return docs[:top_k]
