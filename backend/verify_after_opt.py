# -*- coding: utf-8 -*-
"""一键验证本轮优化是否生效。

覆盖四项：可观测性(trace)、成本控制(缓存/费用)、RAG 混合检索、证据核验。

用法（backend 目录、venv 已激活、uvicorn 已在跑）：
    python verify_after_opt.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
sys.stdout.reconfigure(encoding="utf-8")


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    print("=" * 64)
    print("1) 健康检查")
    try:
        print("   /health ->", get("/health"))
    except urllib.error.URLError as e:
        print("   ✗ 连不上服务。请先在另一个 PowerShell 窗口启动：")
        print("     cd C:\\Users\\ASUS\\Desktop\\appliance-doctor\\backend")
        print("     .venv\\Scripts\\activate")
        print("     uvicorn app.main:app --reload")
        print("   原始错误：", e)
        return

    print("\n2) 指标端点 /api/metrics（新增）")
    try:
        print("   ->", json.dumps(get("/api/metrics"), ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"   ✗ 返回 {e.code} —— 新代码可能没生效，请重启 uvicorn 再试")
        return

    payload = {
        "brand": "海尔",
        "category": "refrigerator",
        "symptom": "冷藏室不制冷，屏幕显示 E1",
        "fault_code": "E1",
        "debug": True,
    }

    print("\n3) 跑一次诊断：看 trace + 证据核验")
    r = post("/api/diagnose", payload)
    if r.get("status") == "need_info":
        print("   （触发了反问，自动回答一轮）")
        r = post("/api/diagnose", {"thread_id": r.get("thread_id"), "answer": "屏幕显示 E1"})

    print("   状态     :", r.get("status"))
    print("   诊断     :", (r.get("diagnosis") or "(空)")[:70])
    print("   安全等级 :", r.get("safety_level"))
    print("   证据核验 : grounded =", r.get("grounded"), "| 证据条数 =", r.get("evidence_count"))
    print("   核验意见 :", r.get("grounding_notes"))

    t = r.get("trace") or {}
    print("\n   --- trace 汇总（新增）---")
    print(f"   耗时 {t.get('total_ms')}ms | {t.get('llm_calls')} 次 LLM 调用 | "
          f"{t.get('total_tokens')} tokens | 缓存命中 {t.get('cache_hits')} | "
          f"费用 {t.get('cost_yuan')} 元")
    print("   --- span 明细（看时间花在哪）---")
    for s in t.get("spans", []):
        meta = s.get("meta") or {}
        extra = "  " + json.dumps(meta, ensure_ascii=False) if meta else ""
        err = s.get("error") or ""
        err_txt = f"  ⚠ERROR: {err}" if err else ""
        print(f"     [{s.get('kind',''):<4}] {s.get('name',''):<26}"
              f"{s.get('duration_ms'):>7}ms  tok={s.get('total_tokens', 0):<5}{extra}{err_txt}")

    # 关键断言：RAG 混合检索是否真的跑了
    # 注意 meta 的 key 是带来源前缀的（fault_code_dense / manual_sparse ...），
    # 所以按后缀汇总，而不是找单个 "sparse" 键。
    rag = next((s for s in t.get("spans", []) if s.get("name") == "rag.retrieve"), None)
    if rag:
        meta = rag.get("meta") or {}
        dense = sum(v for k, v in meta.items() if k.endswith("_dense"))
        sparse = sum(v for k, v in meta.items() if k.endswith("_sparse"))
        print(f"\n   [RAG] 稠密路合计 {dense} 条 + 稀疏路合计 {sparse} 条 "
              f"→ 候选 {meta.get('candidates')} → 返回 {meta.get('returned')}")
        if sparse > 0:
            print("   ✓ 混合检索生效（稠密 + BM25 两路都有结果）")
        else:
            print("   ⚠ 稀疏路为空：BM25 索引可能没建起来（Milvus 里没语料？跑 python ingest.py）")
    else:
        print("\n   ⚠ trace 里没有 rag.retrieve span —— 症状没触发检索？")

    print("\n4) 再发一次相同请求，验证缓存命中")
    r2 = post("/api/diagnose", payload)
    t2 = r2.get("trace") or {}
    print(f"   缓存命中 {t2.get('cache_hits')} 次 | 费用 {t2.get('cost_yuan')} 元（命中不计费）")

    print("\n" + "=" * 64)
    print("检查完成。请把上面的输出整段贴回来，我据此判断是否全部生效。")


if __name__ == "__main__":
    main()
