# -*- coding: utf-8 -*-
"""可观测性：给每次 LLM / 工具 / 图节点调用打点。

设计要点（面试可讲）：
- 用 contextvars 保存「当前 trace」，天然适配多线程与 async，业务代码不用透传参数；
- 每次调用产出一个 Span（名称 / 类型 / 耗时 / token / 输入输出摘要）；
- 一次请求的所有 span 汇总成一条 trace，可落盘、可查询、可告警；
- 默认只记摘要（截断），不把完整 prompt 写进日志，避免泄露与日志膨胀。

用法：
    with span("diagnose", "node", input_preview=symptom) as s:
        ...
        record_usage(s, prompt_tokens=120, completion_tokens=80)
"""
from __future__ import annotations

import contextvars
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

PREVIEW = 200  # 输入/输出摘要的最大字符数

# 落盘目录（trace 日志）；不存在会自动创建
TRACE_DIR = Path(__file__).resolve().parent.parent / "logs"


@dataclass
class Span:
    name: str
    kind: str  # llm | tool | node
    start: float = field(default_factory=time.perf_counter)
    end: float = 0.0
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    input_preview: str = ""
    output_preview: str = ""
    error: str = ""
    cached: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        end = self.end or time.perf_counter()
        return round((end - self.start) * 1000, 1)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("start")
        d.pop("end")
        d["duration_ms"] = self.duration_ms
        d["total_tokens"] = self.total_tokens
        return d


@dataclass
class Trace:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    spans: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "total_ms": round(sum(s.duration_ms for s in self.spans), 1),
            "total_tokens": sum(s.total_tokens for s in self.spans),
            "llm_calls": sum(1 for s in self.spans if s.kind == "llm"),
            "cache_hits": sum(1 for s in self.spans if s.cached),
            "spans": [s.to_dict() for s in self.spans],
        }


_current: contextvars.ContextVar[Optional[Trace]] = contextvars.ContextVar(
    "current_trace", default=None
)


def _cut(text: str, n: int = PREVIEW) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + "…"


def start_trace() -> Trace:
    """开始一条 trace，并设为当前上下文。"""
    t = Trace()
    _current.set(t)
    return t


def get_trace() -> Optional[Trace]:
    return _current.get()


def finish_trace(persist: bool = False) -> Optional[dict]:
    """结束当前 trace，返回字典；persist=True 时落盘到 logs/。"""
    t = _current.get()
    if t is None:
        return None
    data = t.to_dict()
    if persist:
        try:
            TRACE_DIR.mkdir(parents=True, exist_ok=True)
            path = TRACE_DIR / f"trace-{t.trace_id}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            data["path"] = str(path)
        except OSError:
            pass
    _current.set(None)
    return data


@contextmanager
def span(name: str, kind: str, input_preview: str = "", model: str = "", **meta):
    """上下文管理器：自动记录耗时与异常。

        with span("lookup_fault_code", "tool", input_preview=code) as s:
            ...
    """
    s = Span(name=name, kind=kind, input_preview=_cut(input_preview), model=model, meta=meta)
    t = _current.get()
    if t is not None:
        t.spans.append(s)
    try:
        yield s
    except Exception as exc:  # 记录异常后原样抛出，不吞
        s.error = f"{type(exc).__name__}: {exc}"
        s.end = time.perf_counter()
        raise
    else:
        s.end = time.perf_counter()


def record_usage(s: Span, prompt_tokens: int = 0, completion_tokens: int = 0,
                 output: str = "", cached: bool = False) -> None:
    """把 token 用量与输出摘要写回 span。"""
    s.prompt_tokens = prompt_tokens or 0
    s.completion_tokens = completion_tokens or 0
    s.cached = cached
    if output:
        s.output_preview = _cut(output)


def summarize(trace_dict: Optional[dict]) -> str:
    """给人看的一行摘要。"""
    if not trace_dict:
        return "(无 trace)"
    return (
        f"trace {trace_dict['trace_id']}｜{trace_dict['total_ms']}ms｜"
        f"{trace_dict['llm_calls']} 次 LLM｜{trace_dict['total_tokens']} tokens｜"
        f"缓存命中 {trace_dict['cache_hits']}"
    )
