# -*- coding: utf-8 -*-
"""LLM 响应缓存：相同请求直接复用，省 token 也省延迟。

设计要点（面试可讲）：
- **只在确定性输出（temperature ≈ 0）时启用**：否则会把一次随机采样永久固化，
  语义上就是错的。诊断 / 安全审查都是温度 0，所以天然适合缓存。
- key = sha256(model + system + prompt + temperature)，防碰撞。
- 默认进程内 LRU + TTL；配置了 REDIS_URL 则自动切换 Redis，多进程 / 多实例共享。
- Redis 不可用时**静默回退**到内存缓存，绝不让缓存成为故障点。

用法：
    key = cache.make_key(model, system, prompt, temperature)
    if (hit := cache.get(key)) is not None: ...
    cache.set(key, text)
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Optional

from .config import settings


class _MemoryCache:
    """进程内 LRU + TTL。"""

    def __init__(self, maxsize: int = 512, ttl: int = 3600):
        self._d: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = threading.Lock()
        self.maxsize = maxsize
        self.ttl = ttl

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return None
            val, exp = item
            if exp and time.time() > exp:
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return val

    def set(self, key: str, val: str) -> None:
        with self._lock:
            exp = time.time() + self.ttl if self.ttl else 0.0
            self._d[key] = (val, exp)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._d)


_memory: Optional[_MemoryCache] = None
_redis = None
_redis_checked = False
_stats = {"hit": 0, "miss": 0}


def _redis_client():
    """惰性连接 Redis；连不上就标记不可用并回退内存。"""
    global _redis, _redis_checked
    if _redis_checked:
        return _redis or None
    _redis_checked = True
    if not settings.redis_url:
        return None
    try:
        import redis  # 可选依赖

        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


def _backend():
    r = _redis_client()
    if r is not None:
        return r
    global _memory
    if _memory is None:
        _memory = _MemoryCache(maxsize=settings.cache_maxsize, ttl=settings.cache_ttl)
    return _memory


def make_key(model: str, system: str | None, prompt: str, temperature: float) -> str:
    raw = json.dumps(
        {"m": model, "s": system or "", "p": prompt, "t": round(temperature, 3)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "llm:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_generic_key(namespace: str, *parts) -> str:
    """通用缓存键（给检索等非 LLM 结果用）。"""
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{namespace}:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_json(key: str):
    """读 JSON 缓存；未命中或解析失败返回 None。"""
    raw = get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def set_json(key: str, value) -> None:
    try:
        set(key, json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        pass


def invalidate(namespace: str) -> None:
    """清空某个命名空间的缓存。

    当前实现对整个缓存做 clear（内存后端简单有效）；接 Redis 时若需要
    精细失效，可改成按前缀扫描删除。
    """
    if namespace:
        clear()


def get(key: str) -> Optional[str]:
    # 【开关必须在这里拦】早期把 CACHE_ENABLED 的判断放在调用方（llm.py），
    # 结果只挡住了 LLM 缓存，**检索结果缓存照样生效**——
    # 做"关缓存测真实水平"的实验时，指标仍被缓存影响，得出错误结论。
    # 现在把开关下沉到 cache 内部，所有缓存统一受它管。
    if not settings.cache_enabled:
        return None
    try:
        val = _backend().get(key)
    except Exception:
        val = None
    if val:
        _stats["hit"] += 1
    else:
        _stats["miss"] += 1
    return val


def set(key: str, value: str) -> None:  # noqa: A001 - 与 dict 语义一致，便于阅读
    if not settings.cache_enabled:
        return
    try:
        b = _backend()
        if hasattr(b, "setex"):           # Redis
            b.setex(key, settings.cache_ttl, value)
        else:                             # 内存
            b.set(key, value)
    except Exception:
        pass                              # 缓存写入失败不影响主流程


def stats() -> dict:
    total = _stats["hit"] + _stats["miss"]
    return {
        **_stats,
        "hit_rate": round(_stats["hit"] / total, 3) if total else 0.0,
        "backend": "redis" if _redis_client() is not None else "memory",
        "size": len(_memory) if _memory else 0,
    }


def clear() -> None:
    try:
        _backend().clear()
    except Exception:
        pass
    _stats.update(hit=0, miss=0)
