"""多轮诊断端到端测试：新对话 → 收到追问 → 自动回答 → 直到 done。

用 Python 标准库请求，UTF-8 正确解码，避开 PowerShell 的 GBK 乱码问题。
用法（backend 目录、已激活 venv、uvicorn 已在跑）：
    python test_diagnose.py
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")  # 保证中文正常打印

BASE = "http://127.0.0.1:8000"


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    # 1. 模糊提问，触发多轮反问
    r = post(
        "/diagnose",
        {"brand": "海尔", "category": "washing_machine", "symptom": "洗衣机洗着洗着突然停了"},
    )
    print("第1轮:")
    print(json.dumps(r, ensure_ascii=False, indent=2))

    thread_id = r.get("thread_id")
    answers = ["屏幕显示 E1", "排水管没有弯折", "上盖关好了"]

    # 2. 自动回答追问，直到 status=done（最多 3 轮）
    for i in range(3):
        if r.get("status") != "need_info":
            break
        ans = answers[i] if i < len(answers) else "没有"
        r = post("/diagnose", {"thread_id": thread_id, "answer": ans})
        print(f"\n第{i + 2}轮（回答：{ans}）:")
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
