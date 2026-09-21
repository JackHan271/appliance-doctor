"""Milvus 向量库封装（开发用 Milvus Lite）。"""
from .config import settings  # 先加载配置（load_dotenv + 设 MILVUS_URI 环境变量）

from pymilvus import MilvusClient  # 后 import，此时环境变量已就绪，避免 Windows 报 Illegal uri

COLLECTION = "manual_chunks"
# 维度取决于所选 embedding：bge-small-zh-v1.5=512，text-embedding-3-small=1536
# 最终应以实际 embedding 输出维度为准（Phase 2 接入后对齐）。
DIM = 512


def get_client() -> MilvusClient:
    return MilvusClient(settings.milvus_uri)


def init_collection(dim: int = DIM) -> None:
    client = get_client()
    if client.has_collection(COLLECTION):
        return
    client.create_collection(COLLECTION, dimension=dim)


def insert(ids: list[int], vectors: list[list[float]], texts: list[str]) -> None:
    client = get_client()
    init_collection(len(vectors[0]) if vectors else DIM)
    data = [{"id": i, "vector": v, "text": t} for i, v, t in zip(ids, vectors, texts)]
    client.insert(COLLECTION, data)


def search(query_vector: list[float], top_k: int = 5) -> list[dict]:
    """返回最相关片段（含 text 字段）。注意 MilvusClient.search 返回嵌套列表结构。"""
    client = get_client()
    res = client.search(COLLECTION, data=[query_vector], limit=top_k, output_fields=["text"])
    # res 形如 [[{...}, ...]]，取第一层
    return res[0] if res else []
