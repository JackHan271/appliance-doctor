"""诊断图组装（多轮版）：诊断 → 反问 → 证据核验 → 安全审查 → 写长期记忆。

图结构：
START → diagnose → 条件边
    ├─ 信息不足且未达轮数上限 → ask_user（interrupt 反问用户）→ diagnose（循环）
    └─ 否则 → grounding_check → 条件边
                                ├─ 核验不过且未超重试上限 → diagnose（打回重诊）
                                └─ 否则 → safety_review → memory_write → END

记忆体系（三层）：
- 短期：state.history（当前会话问答）
- 会话级摘要：state.summary（早期对话折叠，见 context.compact）
- 长期：user_memory 表（跨会话的用户偏好/结论，首轮注入、结束时写入）
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..config import settings
from ..context import compact, needs_compaction
from ..json_utils import parse_json
from ..llm import chat, chat_with_image
from ..memory import load_memories, remember_from_conversation, render_memories
from ..observability import span
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
0. 【优先级 · 最重要】**先分清"主因"和"顺带提及"**：
   - 若**主因**（诊断排在最前、被结论明确认定的那个原因）属于高压电 / 压缩机 / 制冷剂 /
     主控板 / 传感器 / 加热管 → **判 red**，即使结论里包含"先断电重启观察"这类
     初步自查步骤也不得降级；传感类硬故障不会因为"先自查一下"就变成可自修。
   - 若**主因**是表面可处理的问题（放置不平、门封脏污、温度设置、结霜、异味、噪音等），
     诊断只是**顺带提到**"若无效则可能涉及 X"→ 按**主因**判 green 或 yellow，
     **不得因为"提到过"某个危险部件就判 red**。
   - 判断依据：看诊断**明确建议用户先做什么**，以及结论认定的原因是什么。
1. 涉及高压电、压缩机、制冷剂、主控板、传感器、加热管的，一律判 red；
2. 打开盖板/面板、接触内部部件（清理排水孔/疏通排水管、拆面板清洁）判 yellow，并补充"断电"警示；
3. 完全不打开盖板/面板的表面操作（擦拭门封条/内腔、调温度设置、复位、断电化霜）判 green；只要打开盖板或接触内部部件，至少判 yellow；
4. 「报警 / 提示类」代码按下列口径判，**不要自行放宽或收紧**：
   - H / L（温度提示，非故障）：诊断只含表面自查 → **green**；
   - E6 等超温 / 异常**报警**代码：诊断给出的是自查步骤（查门封、调温度、断电重启）→ **yellow**；
   - 上述两类**一律不得判 red**。
5. 【规则 2–4 的判定依据】以**诊断结论里建议的操作**为准：建议里出现"疏通排水孔 /
   拆面板 / 打开盖板"这类接触内部部件的动作，即使问题本身轻微，也判 yellow。
   注意：本规则**只在根因不属于 red 类时适用**（见规则 0）。

【输出格式】严格输出 JSON，不要输出其他文字：
{"safety_level": "green|yellow|red", "safety_check": "一句话审查意见"}
"""


GROUNDING_SYSTEM = """你是证据核验员。唯一职责：核验【诊断结论】里的每一条关键声称，是否能在【证据片段】中找到支撑。

【核验规则】
1. 只核验「有没有证据支撑」，不评价维修方案本身的好坏，也不重复安全审查的工作。
2. 先把诊断结论拆成若干关键声称（故障原因、涉及部件、故障码含义、处理方法等）。
3. 逐条判断该声称能否在证据片段里找到依据。
4. 判定 grounded：
   - 关键声称大部分有证据支撑 → grounded = true；
   - 关键声称多为无依据的推断、或证据片段为空、或诊断结论为空 → grounded = false。
5. 不确定时保守判 false 并说明，不要为迁就结论而放宽标准。

【输出格式】严格输出 JSON，不要输出其他文字：
{"grounded": true或false, "notes": "一句话核验意见，指出哪些声称缺证据"}
"""

# 证据核验最多打回重诊的次数（防止「诊断→核验→诊断」无限循环）
MAX_GROUNDING_RETRY = 1


def _category_cn(category: str) -> str:
    return "冰箱" if category == "refrigerator" else category


def _build_history_text(summary: str, history: list[dict]) -> str:
    """渲染「滚动摘要 + 最近若干轮」，供提示词使用。

    摘要承载被折叠掉的早期信息（品牌、已排除的原因），
    最近几轮保留原文（细节不能丢）。这就是"短期 + 会话级摘要"的分工。
    """
    parts = []
    if summary:
        parts.append(f"【此前对话摘要】\n{summary}")
    if history:
        lines = ["【最近的问答】"]
        for h in history:
            lines.append(f"- 问：{h.get('q')}")
            lines.append(f"  答：{h.get('a')}")
        parts.append("\n".join(lines))
    return "\n".join(parts) + "\n" if parts else ""


def _summarize_history(text: str) -> str:
    """把一段对话压成摘要。

    注意走 `task="summarize"` —— 会被模型路由到**轻量模型**，
    这类提炼任务不需要强模型，是成本控制的一个具体落点。
    """
    return chat(
        "把下面这段家电维修问答压缩成简明摘要，必须保留：品牌/型号、"
        "用户表达过的偏好、已排除过的原因、已确认的结论。不要编造，300 字以内。\n\n"
        + text,
        system="你是对话摘要助手，只输出摘要正文，不要任何前后缀。",
        task="summarize",
    )


def diagnose(state: DiagnosisState) -> dict:
    """诊断节点：查故障码表 + RAG + LLM 推理，判断信息是否足够。"""
    brand = state.get("brand", "")
    category = state.get("category", "refrigerator")
    symptom = state.get("symptom", "")
    fault_code = state.get("fault_code")

    # ---- 上下文工程：历史超预算时，把最早的部分折叠成滚动摘要 ----
    # 折叠用轻量模型（task="summarize"），而不是硬截断——早期信息（品牌、
    # 已排除的原因）以摘要形式保留下来，不被丢掉。
    summary = state.get("summary", "") or ""
    history = list(state.get("history", []))
    if needs_compaction(history, summary):
        summary, history = compact(summary, history, _summarize_history)

    # ---- 长期记忆：会话首轮注入（跨会话保留的用户偏好 / 事实）----
    memory_text = ""
    if state.get("turn", 0) == 0 and state.get("user_id"):
        memory_text = render_memories(load_memories(state["user_id"]))

    # 有故障码先查确定性表，作为 LLM 推理的锚点
    code_text = ""
    code_info = None
    if fault_code:
        with span("tool.lookup_fault_code", "tool", input_preview=f"{brand}/{fault_code}") as _s:
            code_info = lookup_fault_code(brand, category, fault_code, state.get("load_type"))
            _s.meta["found"] = bool(code_info)
        if code_info:
            code_text = (
                f"故障码 {fault_code} 查表结果：{code_info.get('meaning')}；"
                f"参考安全等级 {code_info.get('level')}。\n"
            )
        else:
            code_text = f"故障码 {fault_code} 未在本地表中查到。\n"

    # RAG：检索与症状相关的参考知识（可用时）
    # 【检索 query 要带上品牌与故障码（实测踩坑）】
    # 只用症状检索时，像「冷藏室不制冷」这种描述，与「故障码 E1：冷藏室传感器
    # 短路或断路」的语义距离不够近，重排模型会把"讲温度控制"的产品功能介绍
    # 排到前面。把品牌和故障码一起拼进 query，故障码语料才能被精准命中。
    rag_text = ""
    rag_hits: list[str] = []
    rag_query = " ".join(x for x in (brand, symptom, fault_code) if x)
    if retrieve is not None and rag_query:
        try:
            with span("tool.rag_retrieve", "tool", input_preview=rag_query) as _s:
                rag_hits = retrieve(rag_query, top_k=3)
                _s.meta["hits"] = len(rag_hits)
            if rag_hits:
                rag_text = "【参考知识（检索结果）】\n" + "\n".join(f"- {h}" for h in rag_hits) + "\n"
        except Exception:
            rag_text = ""

    prompt = (
        f"【品牌】{brand}\n"
        f"【品类】{_category_cn(category)}（{category}）\n"
        f"【症状描述】{symptom or '（用户未提供）'}\n"
        f"{memory_text}"
        f"{code_text}"
        f"{rag_text}"
        f"{_build_history_text(summary, history)}"
        "请按多轮诊断规则，判断信息是否足够，给出诊断或追问。"
    )
    # 被证据核验打回时，把「上一轮缺证据」的反馈带进本轮，避免原地重复
    if state.get("grounding_notes") and state.get("grounding_retries", 0) > 0:
        prompt += (
            f"\n【上一轮核验反馈】{state['grounding_notes']}\n"
            "请只依据上面给出的证据作答；证据不足的推断要明确标注为「不确定」，不要编造。\n"
        )

    # 【关键修复】到达追问轮数上限时，强制本轮必须给出结论。
    # 背景：原提示词写「diagnosis 在 need_more_info=false 时必填」，模型想继续追问时
    # 就把 diagnosis 留空；而轮数一到上限，图会强制转去安全审查，
    # 这个空诊断就一路带进结果 —— 评估里表现为"诊断可用率低、结论空白"。
    # 所以在上限前一轮明确要求收敛：不再追问，必须给总括性结论。
    if state.get("turn", 0) >= state.get("max_turns", 3) - 1:
        prompt += (
            "\n【重要】已达到追问轮数上限，本轮**必须给出诊断结论**：\n"
            "  · need_more_info 必须为 false；\n"
            "  · diagnosis 必须填写，不得留空——即使信息不完整，"
            "也要给出一句总括性结论（如「异味多来自冷藏室内部霉变，请按下面几点排查」），"
            "并明确标注哪些部分因信息不足而无法确定。\n"
        )

    # 有图片时用视觉模型（结合图片内容分析），否则纯文本
    image = state.get("image_base64")
    if image:
        raw = chat_with_image(prompt, image, state.get("media_type") or "image/jpeg", system=DIAGNOSIS_SYSTEM)
    else:
        raw = chat(prompt, system=DIAGNOSIS_SYSTEM)
    parsed = parse_json(raw)

    # 证据 = 确定性查表结果 + RAG 检索片段
    # 【为什么查表结果也算证据】故障码表是**确定性知识**，同样是诊断依据。
    # 若不纳入，核验节点会看不到它，把"E1 = 传感器故障"这类正确结论
    # 误判为"无证据支撑"（假阴性）。两类依据都要给核验员看。
    evidence: list[str] = []
    if code_info:
        evidence.append(
            f"故障码 {fault_code} 查表结果：{code_info.get('meaning')}；"
            f"安全等级 {code_info.get('level')}。"
        )
    evidence.extend(rag_hits)

    # 兜底：到达轮数上限、模型却仍没给出结论时，用已有假设拼一句，
    # 保证空诊断不会流入最终结果（这正是评估里"可用率低"的直接原因）。
    diagnosis = parsed.get("diagnosis")
    if not (diagnosis or "").strip() and state.get("turn", 0) >= state.get("max_turns", 3) - 1:
        hyps = parsed.get("hypotheses") or state.get("hypotheses") or []
        diagnosis = (
            "可能的原因包括：" + "；".join(str(h) for h in hyps) + "。"
            "因信息不足无法进一步确定，建议按上述方向逐项排查，或联系官方售后检测。"
        ) if hyps else "根据现有信息尚不能准确定位，建议补充症状细节，或直接联系官方售后检测。"

    return {
        "hypotheses": parsed.get("hypotheses", []),
        "need_more_info": bool(parsed.get("need_more_info", False)),
        "question": parsed.get("question"),
        "diagnosis": diagnosis,
        "safety_level": parsed.get("safety_level"),
        "evidence": evidence,          # 查表 + RAG，供核验节点比对
        "user_answer": None,           # 清空上一轮的回答
        "turn": state.get("turn", 0) + 1,
        "summary": summary,            # 上下文工程：滚动摘要写回状态
        "history": history,            # 可能被折叠过，写回以保持状态一致
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


def grounding_check(state: DiagnosisState) -> dict:
    """证据核验节点：独立复核诊断结论是否有证据支撑，不达标则打回重诊。

    设计要点：
    这是「生成 → 核验」闭环里的核验环节。核心思路和 safety_review 一致——
    **用一个独立 Agent 去挑战另一个 Agent 的输出**，而不是让生成者自己给自己打分。
    自己给自己打分的问题是"既当运动员又当裁判"，容易放过自己的错。
    """
    evidence = state.get("evidence") or []
    if evidence:
        ev_text = "【证据片段】\n" + "\n".join(
            f"[{i + 1}] {e}" for i, e in enumerate(evidence)
        ) + "\n"
    else:
        ev_text = "【证据片段】（本轮未检索到任何证据）\n"

    prompt = (
        f"【诊断结论】{state.get('diagnosis') or '（空）'}\n"
        f"【诊断假设】{state.get('hypotheses') or []}\n"
        f"{ev_text}"
        "请核验该诊断结论是否有证据支撑。"
    )
    raw = chat(prompt, system=GROUNDING_SYSTEM, task="grounding_check")
    parsed = parse_json(raw)

    grounded = bool(parsed.get("grounded", False))
    if not evidence:
        grounded = False  # 一条证据都没检索到，保守判不达标

    return {
        "grounded": grounded,
        "grounding_notes": parsed.get("notes") or ("本轮无检索证据" if not evidence else ""),
        "grounding_retries": state.get("grounding_retries", 0) + (0 if grounded else 1),
    }


def memory_write(state: DiagnosisState) -> dict:
    """会话结束时把值得长期记住的信息写入长期记忆。

    设计要点：
    - **只在会话结束时写一次**，而不是每轮都写——省调用、避免记忆碎片化；
    - 用轻量模型做抽取（task="summarize" 档位），这类提炼不需要强模型；
    - 按 key upsert，同 key 覆盖即"记忆更新"，天然处理新旧信息冲突；
    - 全流程失败静默（记忆是增强项，不该拖垮诊断主流程）。
    """
    user_id = state.get("user_id")
    if not user_id:
        return {}
    with span("node.memory_write", "node", input_preview=user_id) as s:
        n = remember_from_conversation(
            user_id,
            state.get("symptom", ""),
            state.get("diagnosis") or "",
            state.get("history") or [],
        )
        s.meta["saved"] = n
    return {}


def route_after_diagnose(state: DiagnosisState) -> str:
    if state.get("need_more_info") and state.get("turn", 0) < state.get("max_turns", 3):
        return "ask_user"
    return "grounding_check"  # 信息够了：先核验证据，再走安全审查


def route_after_grounding(state: DiagnosisState) -> str:
    """核验不通过且未超重试上限 → 打回重诊；否则继续安全审查。"""
    if not state.get("grounded", True) and state.get("grounding_retries", 0) <= MAX_GROUNDING_RETRY:
        return "diagnose"
    return "safety_review"


def build_graph(checkpointer=None):
    g = StateGraph(DiagnosisState)
    g.add_node("diagnose", diagnose)
    g.add_node("ask_user", ask_user)
    g.add_node("grounding_check", grounding_check)
    g.add_node("safety_review", safety_review)
    g.add_node("memory_write", memory_write)
    g.add_edge(START, "diagnose")
    g.add_conditional_edges(
        "diagnose",
        route_after_diagnose,
        {"ask_user": "ask_user", "grounding_check": "grounding_check"},
    )
    g.add_edge("ask_user", "diagnose")
    g.add_conditional_edges(
        "grounding_check",
        route_after_grounding,
        {"diagnose": "diagnose", "safety_review": "safety_review"},
    )
    # 安全审查 → 写入长期记忆 → 结束（记忆写入不影响前端拿到的诊断结果）
    g.add_edge("safety_review", "memory_write")
    g.add_edge("memory_write", END)
    # checkpointer 用于支持 interrupt/resume 的状态持久化
    return g.compile(checkpointer=checkpointer or MemorySaver())


def make_checkpointer():
    """创建会话状态 checkpointer：优先 Redis，不可用则回退内存。

    【为什么用 Redis（设计要点）】
    MemorySaver 把会话状态存在进程内存里，后端一重启、多轮对话的 thread 状态全丢，
    用户接着上一轮回答就会失败；也不支持多实例部署。
    换成 RedisSaver 后，checkpoint 持久化到 Redis（依赖 RedisJSON + RediSearch，
    需 Redis Stack），重启后同一 thread_id 仍可继续，多实例也能共享状态。

    【优雅降级】Redis 连不上时**静默回退 MemorySaver**，绝不让存储层故障拖垮服务——
    只是退回"重启丢状态"的老行为，而不是启动失败。
    """
    if not settings.redis_url:
        return MemorySaver()
    try:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_url=settings.redis_url)
        saver.setup()  # 幂等：创建 RediSearch 索引
        return saver
    except Exception:
        return MemorySaver()


def init_graph_with_redis() -> bool:
    """启动时尝试切换到 Redis checkpointer。

    模块级 `graph` 默认用 MemorySaver（保证 import 永不失败）；
    本函数在 FastAPI lifespan 里调用，成功则用 RedisSaver 重建图。
    返回 True 表示已切换，False 表示保持内存态。
    """
    global graph
    if not settings.redis_url:
        return False
    try:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_url=settings.redis_url)
        saver.setup()
        graph = build_graph(checkpointer=saver)
        return True
    except Exception:
        return False


# 模块级默认图：内存 checkpointer，import 永不失败（Redis 在 lifespan 里按需切换）
graph = build_graph()
