"""诊断图组装（多轮版）：诊断 Agent ⇄ 用户反问（interrupt）→ 安全审查 Agent。

图结构：
START → diagnose → 条件边
    ├─ 信息不足且未达轮数上限 → ask_user（interrupt 反问用户）→ diagnose（循环）
    └─ 否则 → safety_review → END
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..json_utils import parse_json
from ..llm import chat, chat_with_image
from ..tools.fault_code import lookup_fault_code
from .state import DiagnosisState

try:
    from ..rag import retrieve
except ImportError:
    retrieve = None

DIAGNOSIS_SYSTEM = """你是资深家电维修诊断专家，服务对象是普通家庭用户。

根据用户提供的品牌、品类、症状、故障码（如有）和已有问答历史，进行多轮诊断。

【多轮诊断规则】
- 先判断信息是否足够定位问题：
  * 信息足够（已有故障码+症状，或症状非常明确）→ need_more_info=false，直接给出诊断结论。
  * 信息不足 → need_more_info=true，给出一个【每次只问一个】、用户能直接回答的追问（如"屏幕显示故障码吗？""门封条是否老化或关不严？""断电重启后是否仍报警？"）。
- 追问必须能帮助收窄假设，不要问无关的或普通用户无法回答的问题（如内部电路测量）。
- 不要重复已经问过的问题。

【报警/提示类代码处理规则 - 必须遵守】
- H/L 是"温度提示"而非故障：只建议调温度设置、检查门封是否关严，判 green。
- E6（超温报警）这类报警代码：先给用户自查步骤（检查门封、温度设置、断电重启），判 yellow；只有在用户明确反馈"自查过仍持续报警"时才升 red。

【三级安全护栏 - 必须严格遵守】
- green（绿）：完全不打开任何盖板/面板的表面操作：擦拭门封条、清理内腔、调温度设置、检查门封外观、复位、断电自然化霜等，无触电/制冷剂风险。
- yellow（黄）：需要打开盖板/面板或接触内部部件（如清理排水孔、疏通排水管、简单拆面板清洁）；必须提醒"先断电再操作"。
- red（红）：涉及高压电、压缩机、制冷剂、主控板、传感器、加热管等；只解释"可能原因"，绝不提供具体维修步骤，建议联系售后。

【输出格式】严格输出 JSON，不要输出其他文字：
{"hypotheses": ["可能原因1", "可能原因2"], "need_more_info": true或false, "question": "追问（仅 need_more_info=true 时填）", "diagnosis": "诊断结论（need_more_info=false 时必填，即使存在多种可能，也要给一句总括性结论，如「异味来自冷藏室内部霉变，请对照下面原因逐项排查」，不要留空）", "safety_level": "green|yellow|red"}
"""

SAFETY_SYSTEM = """你是家电维修安全审查员，独立复核诊断结论的安全性，不受诊断 Agent 结论影响。

【三级护栏】
- green：可安全自修
- yellow：谨慎操作 + 强制断电警示
- red：必须找师傅，只解释原因、不教危险步骤

【复核规则】
1. 涉及高压电、压缩机、制冷剂、主控板、传感器、加热管的，一律判 red；
2. 打开盖板/面板、接触内部部件（清理排水孔/疏通排水管、拆面板清洁）判 yellow，并补充"断电"警示；
3. 完全不打开盖板/面板的表面操作（擦拭门封条/内腔、调温度设置、复位、断电化霜）判 green；只要打开盖板或接触内部部件，至少判 yellow；
4. H/L 温度提示、E6 超温报警等"报警/提示类"代码：若诊断结论只含自查步骤（查门封/调温度/断电重启），判 green 或 yellow，不得直接判 red。

【输出格式】严格输出 JSON，不要输出其他文字：
{"safety_level": "green|yellow|red", "safety_check": "一句话审查意见"}
"""


def _category_cn(category: str) -> str:
    return "冰箱" if category == "refrigerator" else category


def _build_history_text(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["【已进行的问答】"]
    for h in history:
        lines.append(f"- 问：{h.get('q')}")
        lines.append(f"  答：{h.get('a')}")
    return "\n".join(lines) + "\n"


def diagnose(state: DiagnosisState) -> dict:
    """诊断节点：查故障码表 + RAG + LLM 推理，判断信息是否足够。"""
    brand = state.get("brand", "")
    category = state.get("category", "refrigerator")
    symptom = state.get("symptom", "")
    fault_code = state.get("fault_code")
    history = state.get("history", [])

    # 有故障码先查确定性表，作为 LLM 推理的锚点
    code_text = ""
    if fault_code:
        code_info = lookup_fault_code(brand, category, fault_code, state.get("load_type"))
        if code_info:
            code_text = (
                f"故障码 {fault_code} 查表结果：{code_info.get('meaning')}；"
                f"参考安全等级 {code_info.get('level')}。\n"
            )
        else:
            code_text = f"故障码 {fault_code} 未在本地表中查到。\n"

    # RAG：检索与症状相关的参考知识（可用时）
    rag_text = ""
    if retrieve is not None and symptom:
        try:
            hits = retrieve(symptom, top_k=3)
            if hits:
                rag_text = "【参考知识（检索结果）】\n" + "\n".join(f"- {h}" for h in hits) + "\n"
        except Exception:
            rag_text = ""

    prompt = (
        f"【品牌】{brand}\n"
        f"【品类】{_category_cn(category)}（{category}）\n"
        f"【症状描述】{symptom or '（用户未提供）'}\n"
        f"{code_text}"
        f"{rag_text}"
        f"{_build_history_text(history)}"
        "请按多轮诊断规则，判断信息是否足够，给出诊断或追问。"
    )

    # 有图片时用视觉模型（结合图片内容分析），否则纯文本
    image = state.get("image_base64")
    if image:
        raw = chat_with_image(prompt, image, state.get("media_type") or "image/jpeg", system=DIAGNOSIS_SYSTEM)
    else:
        raw = chat(prompt, system=DIAGNOSIS_SYSTEM)
    parsed = parse_json(raw)

    return {
        "hypotheses": parsed.get("hypotheses", []),
        "need_more_info": bool(parsed.get("need_more_info", False)),
        "question": parsed.get("question"),
        "diagnosis": parsed.get("diagnosis"),
        "safety_level": parsed.get("safety_level"),
        "user_answer": None,  # 清空上一轮的回答
        "turn": state.get("turn", 0) + 1,
    }


def ask_user(state: DiagnosisState) -> dict:
    """反问节点：interrupt 挂起图执行，等待用户回答后恢复。"""
    question = state.get("question") or "请补充更多信息"
    answer = interrupt(question)  # 挂起；Command(resume=answer) 时返回 answer
    history = list(state.get("history", []))
    history.append({"q": question, "a": answer})
    checked = list(state.get("checked", []))
    checked.append(question)
    return {"user_answer": answer, "history": history, "checked": checked}


def safety_review(state: DiagnosisState) -> dict:
    """安全审查节点：独立复核安全等级。"""
    prompt = (
        f"诊断结论：{state.get('diagnosis') or '（无）'}\n"
        f"诊断假设：{state.get('hypotheses') or []}\n"
        f"诊断 Agent 给出的初步安全等级：{state.get('safety_level') or '（未给出）'}\n"
        "请复核并给出最终安全等级。"
    )
    raw = chat(prompt, system=SAFETY_SYSTEM)
    parsed = parse_json(raw)

    return {
        "safety_level": parsed.get("safety_level") or state.get("safety_level"),
        "safety_check": parsed.get("safety_check"),
    }


def route_after_diagnose(state: DiagnosisState) -> str:
    if state.get("need_more_info") and state.get("turn", 0) < state.get("max_turns", 3):
        return "ask_user"
    return "safety_review"


def build_graph():
    g = StateGraph(DiagnosisState)
    g.add_node("diagnose", diagnose)
    g.add_node("ask_user", ask_user)
    g.add_node("safety_review", safety_review)
    g.add_edge(START, "diagnose")
    g.add_conditional_edges(
        "diagnose",
        route_after_diagnose,
        {"ask_user": "ask_user", "safety_review": "safety_review"},
    )
    g.add_edge("ask_user", "diagnose")
    g.add_edge("safety_review", END)
    # checkpointer 用于支持 interrupt/resume 的状态持久化（进程内内存）
    return g.compile(checkpointer=MemorySaver())


graph = build_graph()
