"""FastAPI 入口。"""
from uuid import uuid4

from fastapi import FastAPI
from langgraph.types import Command

from .db import Appliance, RepairHistory, SessionLocal, init_db
from .graph.diagnosis import graph
from .tools.fault_code import lookup_fault_code

app = FastAPI(title="Appliance Doctor")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
    """多轮诊断入口。首次 {brand, category, symptom, image_base64?, media_type?}；回答 {thread_id, answer}。"""
    thread_id = payload.get("thread_id") or str(uuid4())
    answer = payload.get("answer")
    config = {"configurable": {"thread_id": thread_id}}

    if answer is not None:
        result = graph.invoke(Command(resume=answer), config=config)
    else:
        initial = {
            k: payload.get(k)
            for k in ("brand", "category", "load_type", "model", "symptom", "fault_code", "image_base64", "media_type")
            if payload.get(k) is not None
        }
        initial.update(
            turn=0,
            max_turns=payload.get("max_turns", 3),
            history=[],
            checked=[],
            hypotheses=[],
        )
        result = graph.invoke(initial, config=config)

    interrupts = result.get("__interrupt__", [])
    if interrupts:
        q = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        return {"status": "need_info", "thread_id": thread_id, "question": q}

    return {
        "status": "done",
        "thread_id": thread_id,
        "diagnosis": result.get("diagnosis"),
        "safety_level": result.get("safety_level"),
        "safety_check": result.get("safety_check"),
        "hypotheses": result.get("hypotheses"),
        "turns": result.get("turn"),
    }


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
