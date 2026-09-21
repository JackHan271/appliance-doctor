"""LLM 接入（可配置 provider：deepseek / anthropic）。

DeepSeek 走 OpenAI 兼容接口，国内直连，无需代理。
"""
from .config import settings


def chat(prompt: str, system: str | None = None, temperature: float = 0.0) -> str:
    """纯文本对话。temperature 默认 0，保证诊断/审查输出的确定性。"""
    if settings.llm_provider == "deepseek":
        return _chat_deepseek(prompt, system, temperature)
    if settings.llm_provider == "anthropic":
        return _chat_anthropic(prompt, system, temperature)
    raise ValueError(f"未知 LLM provider: {settings.llm_provider}")


def _chat_deepseek(prompt: str, system: str | None = None, temperature: float = 0.0) -> str:
    from openai import OpenAI

    if not settings.deepseek_api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 中配置")
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,
        max_tokens=1024,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def _chat_anthropic(prompt: str, system: str | None = None, temperature: float = 0.0) -> str:
    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请在 .env 中配置")
    client = Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": settings.claude_model,
        "max_tokens": 1024,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text")


def chat_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/jpeg",
    system: str | None = None,
) -> str:
    """带图片的对话（铭牌识别 / 故障现象识别）。deepseek 与 anthropic 均支持。"""
    if settings.llm_provider == "deepseek":
        return _chat_deepseek_with_image(prompt, image_base64, media_type, system)
    if settings.llm_provider == "anthropic":
        return _chat_anthropic_with_image(prompt, image_base64, media_type, system)
    raise NotImplementedError(f"当前 LLM provider（{settings.llm_provider}）不支持图片输入")


def _chat_deepseek_with_image(
    prompt: str,
    image_base64: str,
    media_type: str,
    system: str | None,
) -> str:
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
        model=settings.deepseek_vision_model,
        messages=messages,
        max_tokens=1024,
        temperature=0.0,
    )
    return resp.choices[0].message.content or ""


def _chat_anthropic_with_image(
    prompt: str,
    image_base64: str,
    media_type: str,
    system: str | None,
) -> str:
    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请在 .env 中配置")
    client = Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": settings.claude_model,
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
    return "".join(b.text for b in resp.content if b.type == "text")
