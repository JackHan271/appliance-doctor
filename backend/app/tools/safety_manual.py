"""查安全手册工具：RAG 检索通用安全须知。

注意：当前手册库收录的是产品说明书；通用安全手册语料尚未单独采集，
检索结果可能来自产品说明书。接口已就位，补充语料后无需改动代码。
"""
from ..rag import retrieve


def search_safety_manual(query: str, top_k: int = 3) -> list[str]:
    """返回与 query 最相关的安全手册片段（可能为空列表）。"""
    return retrieve(query, top_k=top_k)
