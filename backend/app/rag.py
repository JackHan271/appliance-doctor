"""RAG 检索封装：query → embedding → Milvus search → 文本片段。"""
from .embedding import embed_texts
from .vectordb import search


def retrieve(query: str, top_k: int = 3) -> list[str]:
    """返回与 query 最相关的文本片段（可能为空列表）。"""
    vec = embed_texts([query])[0]
    hits = search(vec, top_k=top_k)
    out = []
    for h in hits:
        text = (h.get("entity") or {}).get("text", "")
        if text:
            out.append(text)
    return out
