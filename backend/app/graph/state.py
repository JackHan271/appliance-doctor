"""LangGraph 诊断状态定义（多轮版）。"""
from typing import TypedDict


class DiagnosisState(TypedDict, total=False):
    brand: str                      # 品牌（海尔/美的/西门子）
    category: str                   # refrigerator（冰箱）
    load_type: str | None           # 历史遗留（洗衣机维度），冰箱不使用
    model: str | None               # 型号（可选）
    symptom: str                    # 用户症状描述
    image_base64: str | None        # 用户上传的图片（base64，不含 data: 前缀）
    media_type: str | None          # 图片 MIME 类型，如 image/jpeg
    fault_code: str | None          # 机器显示的故障码
    hypotheses: list[str]           # 当前假设
    checked: list[str]              # 已排查项
    diagnosis: str | None           # 诊断结论
    safety_level: str | None        # green / yellow / red
    safety_check: str | None        # 安全审查 Agent 输出
    turn: int                       # 已交互轮数
    # 多轮新增
    need_more_info: bool            # 是否需要向用户补充提问
    question: str | None            # 反问用户的问题
    user_answer: str | None         # 用户对反问的回答（每次诊断后清空）
    history: list[dict]             # 问答历史 [{"q": "...", "a": "..."}]
    max_turns: int                  # 最大反问轮数
