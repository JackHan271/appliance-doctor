# -*- coding: utf-8 -*-
"""分层记忆体系（长期记忆层）。

【三层记忆的分工】
  1. **短期记忆**：当前会话的问答历史，存 LangGraph 图状态（`graph/state.py` 的 history）。
  2. **会话级摘要**：早期对话折叠成的滚动摘要（见 `context.py` 的 compact），缓解窗口压力。
  3. **长期记忆**：跨会话持久化的用户信息，存 PostgreSQL，**会话开始时按需注入**、**结束时提取写入**。

【长期记忆的设计取舍（设计要点）】
- **存什么**：只存"会影响未来交互"的稳定信息——家电品牌/型号、表达偏好、
  已确认的结论。不存寒暄、一次性症状描述、中间推理。
- **怎么存**：**结构化 key-value + 分类**，而不是塞整段对话。
  理由：整段对话既冗余又难更新；结构化字段能精确读写、能按 key 覆盖旧值。
- **什么时候写**：会话**结束**时一次性提取，而不是每轮都写——省调用、避免碎片化。
- **冲突怎么处理**：同 key 覆盖并刷新时间戳，这就是最朴素的"记忆更新"；
  需要保留历史时可在表里加软删除或版本字段。
- **为什么不用向量库**：用户偏好这类信息量小、要精确读写，
  结构化库更合适；向量检索适合"模糊语义召回"，两者互补而非替代。
"""
from __future__ import annotations

from .json_utils import parse_json
from .llm import chat
from .observability import span

EXTRACT_SYSTEM = """你从一段家电维修咨询对话中，提取**值得长期记住**的用户信息。

【只提取会持续影响未来交互的稳定信息】
- 用户的家电品牌/型号（如「海尔冰箱」）
- 用户的表达或操作偏好（如「希望步骤尽量简单」「不想自己拆机」）
- 已确认的结论（如「冷藏室不制冷已确认是传感器故障，待联系售后」）

【不要提取】
- 寒暄、一次性的症状描述、中间推理过程
- 通用的家电知识（那些属于知识库，不属于用户记忆）

【输出格式】严格输出 JSON 数组，每项：
{"key": "简短键名（如 品牌 / 偏好 / 结论）", "value": "值", "category": "preference|fact|conclusion"}
若没有值得记住的信息，输出 []。不要输出其他文字。
"""

# category → 渲染时用的标签
_CAT_LABEL = {"preference": "偏好", "fact": "事实", "conclusion": "结论"}


# ---------------------------------------------------------------- 读写（DB）
def load_memories(user_id: str, limit: int = 20) -> list[dict]:
    """读取某用户的长期记忆。失败返回空列表（记忆是增强项，不该拖垮主流程）。"""
    try:
        from .db import SessionLocal, UserMemory

        db = SessionLocal()
        try:
            rows = (
                db.query(UserMemory)
                .filter(UserMemory.user_id == user_id)
                .order_by(UserMemory.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            db.close()
    except Exception:
        return []


def save_memories(user_id: str, items: list[dict]) -> int:
    """按 key upsert：同 key 覆盖（即最简单的「记忆更新 / 冲突消解」）。返回写入条数。"""
    if not items:
        return 0
    try:
        from .db import SessionLocal, UserMemory

        db = SessionLocal()
        try:
            n = 0
            for it in items:
                key = (it.get("key") or "").strip()
                val = (it.get("value") or "").strip()
                if not key or not val:
                    continue
                cat = it.get("category") or "fact"
                row = (
                    db.query(UserMemory)
                    .filter(UserMemory.user_id == user_id, UserMemory.key == key)
                    .first()
                )
                if row:
                    row.value = val
                    row.category = cat
                else:
                    db.add(UserMemory(user_id=user_id, key=key, value=val, category=cat))
                n += 1
            db.commit()
            return n
        finally:
            db.close()
    except Exception:
        return 0


# ---------------------------------------------------------------- 渲染与提取
def render_memories(memories: list[dict]) -> str:
    """把长期记忆渲染成可注入提示词的文本。无记忆时返回空串。"""
    if not memories:
        return ""
    lines = ["【用户长期记忆（来自以往会话）】"]
    for m in memories:
        label = _CAT_LABEL.get(m.get("category", ""), "信息")
        lines.append(f"- [{label}] {m.get('key')}：{m.get('value')}")
    return "\n".join(lines) + "\n"


def extract_memories(conversation_text: str) -> list[dict]:
    """用轻量模型从对话里抽取值得长期记住的信息。

    走 task="summarize" 档位（路由到轻模型）——这类提炼任务不需要强模型，省钱。
    """
    if not (conversation_text or "").strip():
        return []
    with span("memory.extract", "llm", input_preview=conversation_text[:200]) as s:
        raw = chat(conversation_text, system=EXTRACT_SYSTEM, task="summarize")
        parsed = parse_json(raw)
        # 兼容模型偶尔返回 {"items": [...]} 的包法
        if isinstance(parsed, dict):
            parsed = parsed.get("items") or []
        items = [it for it in parsed if isinstance(it, dict)] if isinstance(parsed, list) else []
        s.meta["extracted"] = len(items)
    return items


def remember_from_conversation(user_id: str, symptom: str, diagnosis: str,
                               history: list[dict] | None = None) -> int:
    """会话结束时调用：抽取并写入长期记忆。返回写入条数。"""
    if not user_id:
        return 0
    parts = [f"用户症状：{symptom or '（未提供）'}", f"最终诊断：{diagnosis or '（无）'}"]
    for h in history or []:
        parts.append(f"追问：{h.get('q')}\n用户回答：{h.get('a')}")
    items = extract_memories("\n".join(parts))
    n = save_memories(user_id, items)
    return n
