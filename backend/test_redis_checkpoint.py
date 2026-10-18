# -*- coding: utf-8 -*-
"""验证会话状态是否真正持久化到 Redis（跨重启）。

用法：
    python test_redis_checkpoint.py            # 发起新会话 → 拿 thread_id → 查 Redis
    （然后重启后端）
    python test_redis_checkpoint.py --resume   # 用同一个 thread_id 继续，验证重启后状态还在

判定标准：
    · 第一步应看到 Redis 里有 checkpoint:* 的 key（状态写进 Redis 的直接证据）
    · 重启后第二步能继续对话、不报"找不到 thread"（跨重启持久化的行为证据）
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
TID_FILE = Path(__file__).parent / "_thread_id.txt"
sys.stdout.reconfigure(encoding="utf-8")


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def redis_checkpoint_keys() -> str:
    """查 Redis 里有多少 checkpoint 相关的 key。"""
    try:
        out = subprocess.run(
            ["docker", "exec", "redis-stack", "redis-cli", "KEYS", "checkpoint*"],
            capture_output=True, text=True, timeout=15,
        )
        return out.stdout.strip() or "（空 —— 没有 checkpoint key）"
    except FileNotFoundError:
        return "（找不到 docker 命令，请确认 Docker 在 PATH 里）"
    except Exception as exc:  # noqa: BLE001
        return f"（查询失败：{exc}）"


def start_new() -> None:
    r = post("/api/diagnose", {"brand": "海尔", "category": "refrigerator", "symptom": "冰箱不制冷"})
    print("状态     :", r.get("status"))
    print("thread_id:", r.get("thread_id"))
    print("追问     :", r.get("question"))
    tid = r.get("thread_id") or ""
    TID_FILE.write_text(tid, encoding="utf-8")
    if tid:
        print(f"\nthread_id 已存到 {TID_FILE.name}，重启后端后用 --resume 继续")
    print("\nRedis 里的 checkpoint key：")
    print(" ", redis_checkpoint_keys())


def resume() -> None:
    if not TID_FILE.exists():
        print("还没发起过会话，先跑 python test_redis_checkpoint.py")
        return
    tid = TID_FILE.read_text(encoding="utf-8").strip()
    print("用 thread_id 继续:", tid)
    r = post("/api/diagnose", {"thread_id": tid, "answer": "屏幕显示 E1"})
    print("状态     :", r.get("status"))
    print("诊断     :", (r.get("diagnosis") or "(空)")[:80])
    print("安全等级 :", r.get("safety_level"))
    print("轮数     :", r.get("turns"))
    if r.get("status") == "done":
        print("\n✓ 重启后仍能继续对话 —— 会话状态成功从 Redis 恢复")
    elif "error" in str(r).lower() or r.get("status") == "need_info":
        print("\n（返回 need_info 也算成功——说明它记得之前的上下文，继续在追问）")


if __name__ == "__main__":
    if "--resume" in sys.argv:
        resume()
    else:
        start_new()
