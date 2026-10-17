# -*- coding: utf-8 -*-
"""成本控制：模型路由 + 费用估算。

设计要点（面试可讲）：
- **模型路由**：不是所有任务都值得用最强模型。按任务类型分流——
  诊断/审查/核验这类"要判断准"的走强模型，摘要/分类这类"要跑得快"的走轻模型。
- **价格表驱动**：成本可算、可累计（配合 observability 的 span 汇总成单请求成本）。
- **路由表与价格表都可被环境变量覆盖**，不写死在业务逻辑里。
"""
from __future__ import annotations

from .config import settings

# 每 100 万 token 的价格（元），用于估算，可按 .env 覆盖
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "deepseek-chat": {"in": 2.0, "out": 8.0},
    "deepseek-reasoner": {"in": 4.0, "out": 16.0},
}

# 任务类型 → 模型档位（strong 强 / light 轻 / vision 视觉）
TASK_TIER: dict[str, str] = {
    # 需要判断准确度的：走强模型
    "diagnose": "strong",
    "safety_review": "strong",
    "grounding_check": "strong",
    # 跑得多的轻任务：走轻模型
    "summarize": "light",
    "followup_judge": "light",
    "classify": "light",
    # 视觉任务
    "vision": "vision",
}


def pick_model(task: str = "diagnose") -> str:
    """按任务类型选模型。未知任务按 strong 处理（宁可准，不可错）。"""
    tier = TASK_TIER.get(task, "strong")
    if tier == "light":
        return settings.deepseek_model_light or settings.deepseek_model
    if tier == "vision":
        return settings.deepseek_vision_model
    return settings.deepseek_model_strong or settings.deepseek_model


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算单次调用费用（元）。未收录的模型返回 0。"""
    p = settings.model_prices.get(model) or DEFAULT_PRICES.get(model)
    if not p:
        return 0.0
    return round(prompt_tokens / 1e6 * p["in"] + completion_tokens / 1e6 * p["out"], 6)


def cost_of_trace(trace_dict: dict | None) -> float:
    """把一条 trace 里所有 LLM span 的费用加起来。"""
    if not trace_dict:
        return 0.0
    total = 0.0
    for s in trace_dict.get("spans", []):
        if s.get("kind") == "llm" and not s.get("cached"):  # 缓存命中不计费
            total += estimate_cost(
                s.get("model", ""), s.get("prompt_tokens", 0), s.get("completion_tokens", 0)
            )
    return round(total, 6)
