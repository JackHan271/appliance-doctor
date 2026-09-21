"""Embedding 可配置抽象：bge（本地）/ dashscope（通义）/ openai。

选型由环境变量 EMBEDDING_PROVIDER 决定，业务代码只调用 embed_texts()，
换模型不改业务代码（可配置抽象，面试可讲）。
"""
from .config import settings

_bge_model = None


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = settings.embedding_provider
    if provider == "bge":
        return _embed_bge(texts)
    if provider == "dashscope":
        return _embed_dashscope(texts)
    if provider == "openai":
        return _embed_openai(texts)
    raise ValueError(f"未知 embedding provider: {provider}")


def _embed_bge(texts: list[str]) -> list[list[float]]:
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import SentenceTransformer

        _bge_model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    vecs = _bge_model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def _embed_dashscope(texts: list[str]) -> list[list[float]]:
    import dashscope

    dashscope.api_key = settings.dashscope_api_key
    resp = dashscope.TextEmbedding.call(model="text-embedding-v3", input=texts)
    if resp.status_code != 200:
        raise RuntimeError(f"通义 embedding 失败: {resp.message}")
    return [e["embedding"] for e in resp.output["embeddings"]]


def _embed_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]
