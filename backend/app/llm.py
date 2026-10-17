# -*- coding: utf-8 -*-
"""LLM 接入（可配置 provider：deepseek / anthropic）+ 可观测 + 模型路由 + 响应缓存。

DeepSeek 走 OpenAI 兼容接口，国内直连，无需代理。

设计要点（面试可讲）：
本模块是**所有 LLM 调用的唯一出口**，因此把三个横切关注点都收在这里，
业务代码（诊断图 / 工具）完全不用感知：
  1. 可观测 —— 每次调用打一个 span，记录耗时、token、输入输出摘要；
  2. 成本控制 —— 按 task 路由模型（强/轻），并从 API 返回的 usage 读**真实 token 数**；
  3. 响应缓存 —— temperature≈0 时按 (model+system+prompt) 命中缓存直接复用。
"""
from __future__ import annotations

from . import cache
from .config import settings
from .cost import pick_model
from .observability import record_usage, span


def _resolve_model(task: str, explicit: str | None) -> str:
    """显式指定优先；否则按 provider 与任务类型路由。"""
    if explicit:
        return explicit
    if settings.llm_provider == "anthropic":
        return settings.claude_model
    return pick_model(task)


def _maybe_cached(model: str, system: str | None, prompt: str, temperature: float):
    """返回 (cache_key, cached_text)。未启用缓存或温度>0 时返回 (None, None)。"""
    if not settings.cache_enabled or temperature > 0.0:
        return None, None
    key = cache.make_key(model, system, prompt, temperature)
    return key, cache.get(key)


def chat(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.0,
    task: str = "diagnose",
    model: str | None = None,
) -> str:
    """纯文本对话。temperature 默认 0，保证诊断/审查输出的确定性。

    task 决定模型路由：diagnose / safety_review / grounding_check 走强模型，
    summarize / classify 走轻模型。
    """
    model = _resolve_model(task, model)
    key, cached = _maybe_cached(model, system, prompt, temperature)

    with span("llm.chat", "llm", input_preview=prompt, model=model, task=task) as s:
        if cached is not None:
            record_usage(s, output=cached, cached=True)
            return cached

        if settings.llm_provider == "deepseek":
            text, pt, ct = _chat_deepseek(prompt, system, temperature, model)
        elif settings.llm_provider == "anthropic":
            text, pt, ct = _chat_anthropic(prompt, system, temperature, model)
        else:
            raise ValueError(f"未知 LLM provider: {settings.llm_provider}")

        record_usage(s, pt, ct, output=text)
        if key is not None and text:
            cache.set(key, text)
        return text


def chat_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/jpeg",
    system: str | None = None,
    task: str = "vision",
) -> str:
    """带图片的对话（铭牌识别 / 故障现象识别）。deepseek 与 anthropic 均支持。

    注意：视觉请求**不走缓存**（图片体积大、且复用率低）。
    """
    model = _resolve_model(task, None)
    with span("llm.chat_with_image", "llm", input_preview=prompt, model=model, task=task) as s:
        if settings.llm_provider == "deepseek":
            text, pt, ct = _chat_deepseek_with_image(prompt, image_base64, media_type, system, model)
        elif settings.llm_provider == "anthropic":
            text, pt, ct = _chat_anthropic_with_image(prompt, image_base64, media_type, system, model)
        else:
            raise NotImplementedError(
                f"当前 LLM provider（{settings.llm_provider}）不支持图片输入"
            )
        record_usage(s, pt, ct, output=text)
        return text


# ---------------------------------------------------------------- provider 实现
# 统一返回 (文本, prompt_tokens, completion_tokens)，token 取 API 返回的真实用量。


def _chat_deepseek(prompt: str, system: str | None, temperature: float, model: str):
    from openai import OpenAI

    if not settings.deepseek_api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 中配置")
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1024,
        temperature=temperature,
    )
    usage = getattr(resp, "usage", None)
    return (
        resp.choices[0].message.content or "",
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def _chat_anthropic(prompt: str, system: str | None, temperature: float, model: str):
    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请在 .env 中配置")
    client = Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    usage = getattr(resp, "usage", None)
    return (
        "".join(b.text for b in resp.content if b.type == "text"),
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
    )


def _chat_deepseek_with_image(
    prompt: str, image_base64: str, media_type: str, system: str | None, model: str
):
    from openai import OpenAI

    if not settings.deepseek_api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 中配置")
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    data_url = f"data:{media_type};base64,{image_base64}"
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    )
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1024,
        temperature=0.0,
    )
    usage = getattr(resp, "usage", None)
    return (
        resp.choices[0].message.content or "",
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


def _chat_anthropic_with_image(
    prompt: str, image_base64: str, media_type: str, system: str | None, model: str
):
    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请在 .env 中配置")
    client = Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    usage = getattr(resp, "usage", None)
    return (
        "".join(b.text for b in resp.content if b.type == "text"),
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
    )
