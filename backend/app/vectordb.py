# -*- coding: utf-8 -*-
"""Milvus 向量库封装（开发用 Milvus Lite / gRPC server 模式）—— 支持多知识库。

【为什么要分库（面试可讲）】
故障码表和维修手册是**两种异构知识**：
  · 故障码：结构化、精确、高置信（"E1 = 冷藏室传感器故障，等级 red"）；
  · 手册：  非结构化、宽泛、低置信（讲产品功能与安全须知）。

一开始我把两者混在同一个 collection 里检索，结果实测发现：
**23 条故障码被 85 条手册「淹没」**——因为手册片段更长、对"冷藏室""制冷"
这类查询词的重复次数更多，稠密和稀疏两路都把手册排在前面，
真正相关的故障码反而检索不出来。

所以改成**分库**：故障码与手册各一个 collection，
检索时分别召回、按权重融合（故障码权重更高），
从根上避免"两类知识互相竞争"。
职责也更清晰：确定性知识走查表，非结构化知识走 RAG。

【另外两个踩过的坑】
1. 集合必须 load 才能检索。Milvus 重启后集合会变成 'released'，
   不显式 load 会静默返回空。这里做了自动 load + 识别错误后重载重试。
2. 创建客户端本身也会抛异常（服务没起时 MilvusClient(...) 构造就失败），
   所以凡是可能被上层直接调用的函数，try 必须把 get_client() 也包进去。
"""
from .config import settings  # 先加载配置（load_dotenv + 设 MILVUS_URI 环境变量）

from pymilvus import MilvusClient  # 后 import，此时环境变量已就绪，避免 Windows 报 Illegal uri

# 知识源 → collection 名
COLLECTIONS = {
    "fault_code": "fault_codes",    # 故障码知识（结构化、高置信）
    "manual": "manual_chunks",      # 说明书/手册（非结构化、补充）
}
DEFAULT_SOURCE = "manual"

DIM = 512  # bge-small-zh-v1.5 = 512；text-embedding-3-small = 1536

# 每个 collection 是否已确认 loaded（避免每次检索都多一次 load 往返）
_loaded: dict[str, bool] = {}

_LOAD_HINTS = ("not loaded", "released", "call load", "load state")


def _coll(source: str) -> str:
    """把 source 名映射成 collection 名（允许直接传 collection 名）。"""
    return COLLECTIONS.get(source, source)


def get_client() -> MilvusClient:
    """创建 Milvus 客户端。

    【keepalive 调优（实测踩坑）】日志里能看到 Milvus 返回
    `GOAWAY ... ENHANCE_YOUR_CALM / too_many_pings` —— 说明客户端的 gRPC
    keepalive ping 太频繁，被服务端限流并断连。把间隔调长可以避免。
    不同 pymilvus 版本对连接参数的接受度不同，因此做成"支持则传、不支持则退默认"。
    """
    if settings.milvus_keepalive_ms:
        try:
            return MilvusClient(
                settings.milvus_uri, keepalive_time_ms=settings.milvus_keepalive_ms
            )
        except TypeError:
            pass  # 当前版本不支持该参数，退回默认构造
    return MilvusClient(settings.milvus_uri)


def _ensure_loaded(client: MilvusClient, coll: str) -> None:
    """确保集合已加载。load 幂等，重复调用无害。"""
    if _loaded.get(coll):
        return
    try:
        client.load_collection(coll)
    except Exception:
        pass  # 集合可能还不存在，由调用方兜底
    _loaded[coll] = True


def _reload(client: MilvusClient, coll: str) -> None:
    """强制重新加载（Milvus 重启后集合被卸载时走这里）。"""
    _loaded[coll] = False
    _ensure_loaded(client, coll)


def _is_load_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(h in msg for h in _LOAD_HINTS)


def _with_reload(fn, client: MilvusClient, coll: str):
    """执行 fn；若因集合未加载失败则重载并重试一次。"""
    try:
        return fn()
    except Exception as exc:
        if not _is_load_error(exc):
            raise
        _reload(client, coll)
        return fn()


def init_collection(source: str = DEFAULT_SOURCE, dim: int = DIM) -> None:
    """建集合（幂等）并确保 loaded。"""
    coll = _coll(source)
    client = get_client()
    if not client.has_collection(coll):
        client.create_collection(coll, dimension=dim)
    _ensure_loaded(client, coll)


def drop(source: str) -> None:
    """删除某个 collection（重建语料时用，保证幂等）。"""
    coll = _coll(source)
    client = get_client()
    if client.has_collection(coll):
        client.drop_collection(coll)
    _loaded.pop(coll, None)


def insert(source: str, ids: list[int], vectors: list[list[float]], texts: list[str]) -> None:
    coll = _coll(source)
    client = get_client()
    init_collection(source, len(vectors[0]) if vectors else DIM)
    data = [{"id": i, "vector": v, "text": t} for i, v, t in zip(ids, vectors, texts)]
    client.insert(coll, data)


def search(source: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    """在指定知识库做向量检索。集合被卸载时自动重载重试。"""
    coll = _coll(source)
    client = get_client()
    _ensure_loaded(client, coll)
    res = _with_reload(
        lambda: client.search(coll, data=[query_vector], limit=top_k, output_fields=["text"]),
        client, coll,
    )
    return res[0] if res else []


def all_texts(source: str = DEFAULT_SOURCE, limit: int = 10000) -> list[str]:
    """取出某知识库全部语料（供内存 BM25 索引使用）。失败返回空列表。"""
    coll = _coll(source)
    try:
        client = get_client()
        _ensure_loaded(client, coll)
        rows = _with_reload(
            lambda: client.query(coll, filter="id >= 0", output_fields=["text"], limit=limit),
            client, coll,
        )
        return [r.get("text", "") for r in rows if r.get("text")]
    except Exception:
        return []


def health() -> dict:
    """各知识库的连通性、加载状态与条数。暴露到 /api/metrics，避免静默失败难排查。"""
    out: dict = {}
    try:
        client = get_client()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    for source, coll in COLLECTIONS.items():
        try:
            if not client.has_collection(coll):
                out[source] = {"ok": True, "count": 0, "note": "集合不存在，需先 ingest"}
                continue
            _ensure_loaded(client, coll)
            rows = _with_reload(
                lambda c=coll: client.query(c, filter="id >= 0", output_fields=["count(*)"]),
                client, coll,
            )
            out[source] = {
                "ok": True,
                "collection": coll,
                "count": rows[0].get("count(*)") if rows else 0,
                "loaded": True,
            }
        except Exception as exc:
            out[source] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    out["ok"] = all(v.get("ok") for k, v in out.items() if isinstance(v, dict))
    return out
