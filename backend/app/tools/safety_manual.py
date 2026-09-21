"""查安全手册工具：RAG 检索通用安全须知。

注意：当前向量库入库的是故障码语料；通用安全手册语料待采集入库后，
本工具即可检索到安全须知内容（接口已就位，无需改动）。
"""
from ..rag import retrieve


def search_safety_manual(query: str, top_k: int = 3) -> list[str]:
    """返回与 query 最相关的安全手册片段（可能为空列表）。"""
    return retrieve(query, top_k=top_k)
