"""FastAPI 入口。"""
import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from langgraph.types import Command
from starlette.concurrency import run_in_threadpool

from . import cache, observability
from .cost import cost_of_trace
from .db import Appliance, RepairHistory, SessionLocal, init_db
from .graph import diagnosis as dg
from .tools.fault_code import lookup_fault_code


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表、切换 Redis checkpointer、后台预热本地模型。

    用 lifespan 取代已弃用的 @app.on_event("startup")
    （FastAPI 新版推荐写法，启动/关闭逻辑集中在一处）。
    """
    init_db()

    # 尝试把会话状态 checkpointer 从内存切到 Redis（跨重启持久化）。
    # 失败静默回退内存，不阻塞启动。
    from .graph.diagnosis import init_graph_with_redis

    redis_ok = init_graph_with_redis()
    print(f"[lifespan] 会话状态 checkpointer：{'Redis（跨重启持久化）' if redis_ok else '内存（重启即丢）'}")

    # 后台线程预热本地模型，不阻塞服务启动
    import threading

    threading.Thread(target=_warmup_models, daemon=True).start()
    yield


app = FastAPI(title="Appliance Doctor", lifespan=lifespan)


def _warmup_models() -> None:
    """预热本地模型（BGE embedding + Cross-Encoder 重排）。

    实测：重排模型首次加载约 40 秒，若发生在用户请求里就是"第一枪特别慢"。
    启动时预热一次，把这份成本从请求路径上挪走。
    失败静默——预热失败不影响可用性（真正调用时会再尝试加载）。
    """
    import os

    if os.getenv("WARMUP_MODELS", "1") in ("0", "false", "False"):
        return
    try:
        from .embedding import embed_texts

        embed_texts(["预热"])
    except Exception:
        pass
    try:
        from .rerank import warmup

        warmup()
    except Exception:
        pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/tools/fault-code")
def fault_code(brand: str, category: str, code: str, load_type: str | None = None) -> dict:
    result = lookup_fault_code(brand, category, code, load_type)
    if result is None:
        return {"found": False}
    return {"found": True, **result}


@app.post("/api/diagnose")
def diagnose(payload: dict) -> dict:
    """多轮诊断入口（同步返回）。首次 {brand, category, symptom, image_base64?, media_type?}；回答 {thread_id, answer}。

    每次请求开一条 trace，记录本请求内所有 LLM 调用的耗时/token/缓存命中，
    随响应一并返回（可用 debug=true 查看完整 span）。
    """
    return _diagnose_sync(payload)


def _diagnose_sync(payload: dict) -> dict:
    """诊断主逻辑（同步）。被同步端点与后台任务共用。"""
    thread_id = payload.get("thread_id") or str(uuid4())
    answer = payload.get("answer")
    config = {"configurable": {"thread_id": thread_id}}

    observability.start_trace()
    try:
        if answer is not None:
            result = dg.graph.invoke(Command(resume=answer), config=config)
        else:
            initial = {
                k: payload.get(k)
                for k in ("brand", "category", "load_type", "model", "symptom", "fault_code",
                          "image_base64", "media_type", "user_id")
                if payload.get(k) is not None
            }
            initial.update(
                turn=0,
                max_turns=payload.get("max_turns", 3),
                history=[],
                checked=[],
                hypotheses=[],
                summary="",           # 上下文工程：滚动摘要初始为空
            )
            result = dg.graph.invoke(initial, config=config)
    finally:
        trace = observability.finish_trace()

    interrupts = result.get("__interrupt__", [])
    if interrupts:
        q = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        return {"status": "need_info", "thread_id": thread_id, "question": q, "trace": _trace_brief(trace)}

    return {
        "status": "done",
        "thread_id": thread_id,
        "diagnosis": result.get("diagnosis"),
        "safety_level": result.get("safety_level"),
        "safety_check": result.get("safety_check"),
        "hypotheses": result.get("hypotheses"),
        "turns": result.get("turn"),
        # 证据核验结果：是否被检索证据支撑、核验意见、检回的证据条数
        "grounded": result.get("grounded"),
        "grounding_notes": result.get("grounding_notes"),
        "evidence_count": len(result.get("evidence") or []),
        "trace": _trace_brief(trace, detail=bool(payload.get("debug"))),
    }


def _trace_brief(trace: dict | None, detail: bool = False) -> dict | None:
    """给响应附上 trace 摘要（默认只给汇总，debug 时给完整 span）。"""
    if not trace:
        return None
    brief = {
        "trace_id": trace["trace_id"],
        "total_ms": trace["total_ms"],
        "total_tokens": trace["total_tokens"],
        "llm_calls": trace["llm_calls"],
        "cache_hits": trace["cache_hits"],
        "cost_yuan": cost_of_trace(trace),
    }
    if detail:
        brief["spans"] = trace["spans"]
    return brief


@app.get("/api/metrics")
def metrics() -> dict:
    """运行指标：缓存命中率、各知识库连通性与条数。可直接接 Prometheus/Grafana。"""
    from .vectordb import health as vectordb_health

    return {"cache": cache.stats(), "vectordb": vectordb_health()}


@app.post("/api/admin/reindex")
def reindex() -> dict:
    """刷新进程内的关键词索引。

    重新灌库后，运行中的后端仍持有旧语料构建的 BM25 索引；
    调本端点即可刷新，**不必重启服务**。
    """
    from .rag import reset_indexes

    reset_indexes()
    return {"ok": True, "message": "关键词索引与检索缓存已刷新（下次检索会用新语料重建）"}


@app.get("/api/health/services")
def services_health() -> dict:
    """依赖服务体检：向量库 + 业务数据库。

    单独做一个端点，是为了把"服务没起"这类问题**变成一眼可见的显式报错**——
    否则表现只是"检索返回空""接口 500"，排查成本很高。
    """
    from .vectordb import health as vectordb_health

    db_ok, db_err = True, ""
    try:
        from sqlalchemy import text

        from .db import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok, db_err = False, f"{type(exc).__name__}: {exc}"

    vdb = vectordb_health()
    return {
        "ok": bool(vdb.get("ok")) and db_ok,
        "vectordb": vdb,
        "database": {"ok": db_ok, "error": db_err},
    }


# ---------- 异步诊断任务 ----------
# 一次多轮诊断可能耗时几十秒到几分钟，同步请求会一直占着 HTTP 连接
# （容易触发网关/浏览器超时）。异步化后：提交即返回 job_id，连接立刻释放，
# 长任务在服务端跑，客户端轮询取结果。
#
# 说明：这是进程内的任务表。生产环境应换成 Redis/Celery 之类的持久化队列，
# 才能支持多实例与重启恢复；这里保持零额外依赖，够单机 demo 用。

_jobs: dict[str, dict] = {}
JOB_TTL_SECONDS = 3600


def _gc_jobs() -> None:
    """清理过期任务，避免内存无限增长。"""
    now = time.time()
    for jid in [k for k, v in _jobs.items() if now - v.get("created", now) > JOB_TTL_SECONDS]:
        _jobs.pop(jid, None)


async def _run_diagnose_job(job_id: str, payload: dict) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        # 诊断逻辑是同步阻塞的（LLM SDK 调用），必须丢进线程池，
        # 否则会卡住事件循环、拖垮同一进程内的其他请求。
        result = await run_in_threadpool(_diagnose_sync, payload)
        _jobs[job_id].update(status="done", result=result)
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id].update(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/diagnose/submit")
async def diagnose_submit(payload: dict) -> dict:
    """提交后台诊断任务，立即返回 job_id。"""
    _gc_jobs()
    job_id = uuid4().hex[:12]
    _jobs[job_id] = {"status": "queued", "created": time.time()}
    asyncio.create_task(_run_diagnose_job(job_id, payload))
    return {"job_id": job_id, "status": "queued", "poll": f"/api/diagnose/job/{job_id}"}


@app.get("/api/diagnose/job/{job_id}")
def diagnose_job(job_id: str) -> dict:
    """查询后台诊断任务的状态与结果。"""
    job = _jobs.get(job_id)
    if not job:
        return {"status": "not_found", "job_id": job_id}
    return {"job_id": job_id, **job}


# ---------- 长期记忆 ----------
# 记忆在会话结束时由 memory_write 节点自动写入；这里提供查看与清理。

@app.get("/api/memory")
def list_memory(user_id: str = "default") -> list[dict]:
    """查看某用户的长期记忆（跨会话保留的偏好 / 事实 / 结论）。"""
    from .memory import load_memories

    return load_memories(user_id)


@app.delete("/api/memory")
def clear_memory(user_id: str = "default") -> dict:
    """清空某用户的长期记忆。"""
    try:
        from .db import SessionLocal, UserMemory

        db = SessionLocal()
        try:
            n = db.query(UserMemory).filter(UserMemory.user_id == user_id).delete()
            db.commit()
            return {"ok": True, "deleted": n}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------- 个人家电名单 CRUD ----------

@app.get("/api/appliances")
def list_appliances() -> list[dict]:
    db = SessionLocal()
    try:
        return [a.to_dict() for a in db.query(Appliance).order_by(Appliance.id).all()]
    finally:
        db.close()


@app.post("/api/appliances")
def create_appliance(payload: dict) -> dict:
    db = SessionLocal()
    try:
        a = Appliance(
            brand=payload.get("brand", ""),
            model=payload.get("model", ""),
            category=payload.get("category", "冰箱"),
            category_en=payload.get("category_en", "refrigerator"),
            purchase_date=payload.get("date", ""),
            warranty=payload.get("warranty", ""),
        )
        db.add(a)
        db.commit()
        db.refresh(a)
        return a.to_dict()
    finally:
        db.close()


@app.delete("/api/appliances/{aid}")
def delete_appliance(aid: int) -> dict:
    db = SessionLocal()
    try:
        a = db.get(Appliance, aid)
        if a:
            db.delete(a)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


# ---------- 维修历史 CRUD ----------

@app.get("/api/history")
def list_history() -> list[dict]:
    db = SessionLocal()
    try:
        return [h.to_dict() for h in db.query(RepairHistory).order_by(RepairHistory.id.desc()).all()]
    finally:
        db.close()


@app.post("/api/history")
def create_history(payload: dict) -> dict:
    db = SessionLocal()
    try:
        h = RepairHistory(
            brand=payload.get("brand", ""),
            model=payload.get("model", ""),
            level=payload.get("level", "yellow"),
            issue=payload.get("issue", ""),
            detail=payload.get("detail", ""),
        )
        db.add(h)
        db.commit()
        db.refresh(h)
        return h.to_dict()
    finally:
        db.close()


@app.delete("/api/history/{hid}")
def delete_history(hid: int) -> dict:
    db = SessionLocal()
    try:
        h = db.get(RepairHistory, hid)
        if h:
            db.delete(h)
            db.commit()
        return {"ok": True}
    finally:
        db.close()
