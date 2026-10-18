# -*- coding: utf-8 -*-
"""轻量 BM25 关键词检索（纯 Python，零依赖）。

为什么需要它（设计要点）：
向量检索擅长**语义相近**（"不制冷" ≈ "温度降不下来"），但在**精确词**上很弱——
型号、故障码（E1）、专有名词、参数这类"字面必须命中"的东西，向量经常召回不到。
所以工业 RAG 普遍用「稠密 + 稀疏」混合检索：

    稠密抓语义，BM25 抓精确，再用 RRF 融合两路排名。

中文分词取巧：不做词法分析（避免引入 jieba），直接用**字符二元组（bigram）**，
对中文短文本效果足够，且零依赖。

BM25 打分公式（k1 控制词频饱和，b 控制长度归一化）：
    score(q, d) = Σ IDF(qi) · (f(qi,d)·(k1+1)) / (f(qi,d) + k1·(1-b+b·|d|/avgdl))
"""
from __future__ import annotations

import math
from collections import Counter


def tokenize(text: str) -> list[str]:
    """中英混合的简易切分：英文/数字按词，中文按字符二元组。"""
    tokens: list[str] = []
    buf = ""
    for ch in text or "":
        if ch.isascii() and (ch.isalnum() or ch in "-_."):
            buf += ch.lower()
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            if ch.strip():
                tokens.append(ch)  # 单字
    if buf:
        tokens.append(buf)

    # 中文二元组：把连续的中文字符串也补上 bigram，提升区分度
    chinese = [c for c in (text or "") if "一" <= c <= "鿿"]
    tokens.extend(chinese[i] + chinese[i + 1] for i in range(len(chinese) - 1))
    return tokens


class BM25:
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = list(corpus)
        self.docs = [tokenize(t) for t in self.corpus]
        self.doc_len = [len(d) for d in self.docs]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.tf: list[Counter] = [Counter(d) for d in self.docs]

        # IDF：出现过该词的文档数
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf: dict[str, float] = {
            w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()
        }

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """返回 [(语料下标, 分数)]，按分数降序。分数为 0 的不返回。"""
        if not self.docs:
            return []
        q_terms = tokenize(query)
        if not q_terms:
            return []

        scores: list[tuple[int, float]] = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            dl = self.doc_len[i] or 1
            for term in q_terms:
                f = tf.get(term)
                if not f:
                    continue
                idf = self.idf.get(term, 0.0)
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if s > 0:
                scores.append((i, s))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion：只看排名不看分数，天然规避"两路分数不可比"的问题。

        score(d) = Σ 1 / (k + rank_i(d))

    k=60 是论文里的鲁棒默认值。返回融合后的文档下标列表（降序）。
    这是纯函数，便于单测。
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return [d for d, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]


def rrf_weighted(rankings: list[tuple[list, float]], k: int = 60) -> list:
    """加权版 RRF：每个召回列表带一个权重。

        score(d) = Σ w_i / (k + rank_i(d))

    【为什么需要权重（设计要点）】
    多知识库检索时，各库的"权威度"不同。故障码表是结构化、精确、高置信的；
    维修手册是非结构化、宽泛的。若等权融合，**数量更多、片段更长的手册会把
    故障码挤下去**（实测：23 条故障码被 85 条手册完全淹没）。
    给故障码更高权重，就能让两类知识按"可信度"而非"数量"参与排序。

    入参 rankings 形如 [(文档列表, 权重), ...]，文档可以是任意可哈希对象
    （下标、文本都可以）。返回按融合分降序的文档列表。
    """
    fused: dict = {}
    for ranking, weight in rankings:
        for rank, doc in enumerate(ranking):
            fused[doc] = fused.get(doc, 0.0) + weight / (k + rank + 1)
    return [d for d, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]
