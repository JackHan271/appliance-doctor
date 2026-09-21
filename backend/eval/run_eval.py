"""评估 harness：跑评估集、调 /diagnose、统计安全指标、输出报告。

用法（backend 目录、已激活 venv、uvicorn 已在跑）：
    python -m eval.run_eval

输出：
- 每个用例的 expected / actual / 命中情况
- 汇总指标：安全等级准确率、偏严（安全方向）、偏松（危险方向，含 red 漏报红线）、诊断可用率
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
CASES_PATH = Path(__file__).parent / "cases.json"

ORDER = {"green": 0, "yellow": 1, "red": 2}


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def diagnose_case(case: dict) -> dict:
    """对单个用例跑诊断；若触发追问，自动循环回答（最多 3 轮）。"""
    payload = {
        k: case[k]
        for k in ("brand", "category", "load_type", "symptom", "fault_code")
        if case.get(k)
    }
    r = post("/api/diagnose", payload)
    answers = [
        f"屏幕显示 {case.get('fault_code', 'E1')}",
        "没有其他异常",
        "已经断电检查过了",
    ]
    for i in range(3):
        if r.get("status") != "need_info":
            break
        ans = answers[i] if i < len(answers) else "没有"
        r = post("/api/diagnose", {"thread_id": r.get("thread_id"), "answer": ans})
    return r


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]

    total = 0
    correct_level = 0
    over_strict = 0       # 偏严（安全方向）：判的等级比标准高
    under_strict = 0      # 偏松（危险方向）：判的等级比标准低
    dangerous_miss = 0    # red 被降级（红线，必须为 0）
    usable = 0
    need_info_count = 0

    rows = []
    for c in cases:
        total += 1
        r = diagnose_case(c)
        actual = r.get("safety_level")
        exp = c["expected_level"]
        diag = r.get("diagnosis") or ""

        if r.get("status") == "need_info":
            need_info_count += 1

        ai = ORDER.get(actual, -1)
        ei = ORDER.get(exp, -1)
        if actual == exp:
            correct_level += 1
        elif ai > ei:
            over_strict += 1
        elif ai < ei:
            under_strict += 1
            if exp == "red":
                dangerous_miss += 1

        kws = c.get("expected_keywords", [])
        if kws and any(k in diag for k in kws):
            usable += 1

        rows.append(
            {
                "id": c["id"],
                "expected": exp,
                "actual": actual or "未得出",
                "hit": actual == exp,
                "usable": bool(kws and any(k in diag for k in kws)),
                "diagnosis_preview": (diag[:60] + "…") if len(diag) > 60 else diag,
            }
        )

    # 输出报告
    print("=" * 60)
    print(f"评估集：{data['name']}（{total} 个用例）")
    print("=" * 60)
    for r in rows:
        flag = "✓" if r["hit"] else "✗"
        print(f"[{flag}] {r['id']:<20} 期望={r['expected']:<6} 实际={r['actual']:<6} 可定位={'是' if r['usable'] else '否'}")
        print(f"     {r['diagnosis_preview']}")

    print("\n" + "=" * 60)
    print("汇总指标")
    print("=" * 60)
    print(f"安全等级准确率：{correct_level}/{total} = {correct_level / total * 100:.1f}%")
    print(f"偏严（安全方向，判得更保守）：{over_strict} 例")
    print(f"偏松（危险方向，判得更宽松）：{under_strict} 例")
    print(f"  其中危险漏报（red 被降级，红线应为 0）：{dangerous_miss} 例")
    print(f"诊断可用率（命中关键词）：{usable}/{total} = {usable / total * 100:.1f}%")
    print(f"触发追问的用例数：{need_info_count}")

    # 导出明细
    out = {
        "summary": {
            "total": total,
            "level_accuracy": correct_level / total if total else 0,
            "over_strict": over_strict,
            "under_strict": under_strict,
            "dangerous_miss": dangerous_miss,
            "usable": usable,
        },
        "rows": rows,
    }
    out_path = Path(__file__).parent / "report.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已写入 {out_path}")


if __name__ == "__main__":
    main()
