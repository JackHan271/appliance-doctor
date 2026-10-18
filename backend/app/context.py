# -*- coding: utf-8 -*-
"""上下文工程：token 预算、历史裁剪、滚动摘要触发。

【为什么需要（设计要点）】
上下文窗口是 Agent 最稀缺的资源。不管理会有两个典型问题：
  1. 历史越堆越长 → 成本线性上升、延迟变高、关键信息被噪声淹没；
  2. 直接硬截断 → 早期的重要约束（品牌、"已经排除过 X 原因"）被丢掉。

所以按「预算」管理而不是按「条数」管理：
  · 估算各部分的 token 占用（本地估算，不调 tokenizer）；
  · 历史超预算时，把最早的部分**折叠成摘要**而不是丢弃；
  · 摘要自身也有长度上限，避免它自己无限膨胀。

【与记忆体系的分工】
本模块只管**当前会话内的上下文**（短期 + 会话级摘要）；
跨会话的长期记忆在 `memory.py`。
"""
from __future__ import annotations

import re

from .config import settings

# 中日韩字符
_CJK = re.compile(r"[一-鿿぀-ヿ]")
# 英文单词
_WORD = re.compile(r"[A-Za-z0-9]+")


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    规则：CJK 字符按 ~1 token/字，英文/数字按 ~1.3 token/词，其余（标点空白）按 0.3。
    只用于**预算控制**，不追求精确——精确计数需要对应模型的 tokenizer，
    而这里的目标只是"别把窗口撑爆"。
    """
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    others = max(0, len(text) - cjk - sum(len(w) for w in _WORD.findall(text)))
    return int(cjk * 1.0 + words * 1.3 + others * 0.3) + 1


def format_turns(history: list[dict]) -> str:
    """把若干轮问答渲染成文本（供摘要与提示词使用）。"""
    lines = []
    for h in history:
        lines.append(f"问：{h.get('q')}")
        lines.append(f"答：{h.get('a')}")
    return "\n".join(lines)


def budget_report(parts: dict[str, str]) -> dict:
    """统计各部分的 token 占用与预算占比（便于观察与调参）。"""
    total = sum(estimate_tokens(v) for v in parts.values())
    budget = settings.context_budget_tokens
    return {
        "tokens": {k: estimate_tokens(v) for k, v in parts.items()},
        "total": total,
        "budget": budget,
        "usage": round(total / budget, 3) if budget else 0.0,
        "over_budget": total > budget,
    }


def needs_compaction(history: list[dict], summary: str = "") -> bool:
    """判断是否需要折叠早期历史。

    触发条件（任一）：
      · 保留轮数超过 `history_keep_turns`；
      · 历史 + 摘要的估算 token 超过 `context_budget_tokens`。
    """
    if len(history) > settings.history_keep_turns:
        return True
    used = estimate_tokens(summary) + estimate_tokens(format_turns(history))
    return used > settings.context_budget_tokens


def split_for_compaction(history: list[dict]) -> tuple[list[dict], list[dict]]:
    """把历史拆成 (要折叠的早期部分, 要保留的最近部分)。"""
    keep = max(1, settings.history_keep_turns)
    if len(history) <= keep:
        return [], history
    return history[:-keep], history[-keep:]


def compact(summary: str, history: list[dict], summarize_fn) -> tuple[str, list[dict]]:
    """执行一次压缩：把最早的历史折叠进摘要。

    `summarize_fn(text) -> str` 由调用方注入（通常走轻量模型），
    这样本模块不依赖 LLM，便于单测。
    失败时**原样返回**，绝不因为压缩失败而丢掉历史。
    """
    old_turns, recent = split_for_compaction(history)
    if not old_turns:
        return summary, history
    try:
        merged = (summary + "\n" + format_turns(old_turns)).strip()
        new_summary = summarize_fn(merged)
        if not (new_summary or "").strip():
            return summary, history
        # 摘要自身也要限长，避免越滚越大
        limit = settings.summary_max_chars
        if len(new_summary) > limit:
            new_summary = new_summary[:limit] + "…"
        return new_summary, recent
    except Exception:
        return summary, history
