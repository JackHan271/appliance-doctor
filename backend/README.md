# 后端 · Appliance Doctor

FastAPI + LangGraph 多 Agent 诊断服务。

## 目录结构

```
backend/
  app/
    main.py            # FastAPI 入口：诊断、CRUD、trace、指标
    config.py          # 配置（环境变量，含模型路由 / 缓存 / 检索参数）
    llm.py             # LLM 唯一出口：模型路由 + 响应缓存 + 埋点
    graph/
      state.py         # LangGraph 状态定义
      diagnosis.py     # 诊断图：诊断 / 反问 / 证据核验 / 安全审查
    tools/
      fault_code.py    # 查故障码（确定性查表）
      nameplate.py     # 铭牌识别（视觉）
      symptom.py       # 故障现象识别（视觉）
      safety_manual.py # 安全手册检索
    mcp_server.py      # 以 MCP 协议暴露上述工具（stdio / Streamable HTTP）
    rag.py             # 分库混合检索：稠密 + BM25 → RRF → 重排
    bm25.py            # 自实现 BM25 与 RRF（零依赖）
    rerank.py          # Cross-Encoder 重排
    vectordb.py        # Milvus 多库封装（fault_codes / manual_chunks）
    embedding.py       # Embedding 抽象（bge / dashscope / openai）
    observability.py   # trace / span 埋点（contextvars）
    cost.py            # 任务级模型路由与费用估算
    memory.py          # 三层记忆的长期层（user_memory 表）
    context.py         # 上下文工程：token 预算 + 滚动摘要
    cache.py           # 响应缓存（内存 LRU / Redis，自动降级）
    db.py              # PostgreSQL 模型
  ingest.py            # 统一语料入库（分库 + 中文过滤 + 幂等）
  diagnose_rag.py      # RAG 链路逐段排查
  verify_after_opt.py  # 优化项验证
  eval/                # 评估集 + harness
  scripts/             # 辅助脚本
```

## 本机运行（Windows PowerShell）

### 前置

- Python ≥ 3.12，已建虚拟环境 `backend/.venv`
- `backend/.env` 配好 `DEEPSEEK_API_KEY` 与 `DATABASE_URL`
- PostgreSQL 已建库 `appliance_doctor`

### 快速启动

双击 `启动Milvus.bat` 与 `启动后端.bat`（窗口标题会标注「请勿关闭」）。

或手动：

```powershell
# ① Milvus（常开；关掉则 RAG 检索失效）
cd backend; .venv\Scripts\Activate.ps1
milvus-lite server --data-dir ./milvus_data --port 19530

# ② 后端
cd backend; .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

验证：`http://127.0.0.1:8000/health` 应返回 `{"status":"ok"}`。

### 首次灌语料

```powershell
cd backend; .venv\Scripts\Activate.ps1
python ingest.py                # 故障码 + 中文手册，分两个知识库写入
python ingest.py --no-manuals   # 只入故障码（快，适合验证链路）
```

重新灌库后需重启后端，或调 `POST /api/admin/reindex` 刷新进程内关键词索引。

## 关键设计

### 诊断图（`graph/diagnosis.py`）

```
START → diagnose → 条件边
    ├─ 信息不足且未达轮数上限 → ask_user（interrupt 反问）→ diagnose（循环）
    └─ 否则 → grounding_check → 条件边
                                  ├─ 核验不过且未超重试上限 → diagnose（打回重诊）
                                  └─ 否则 → safety_review → memory_write → END
```

- **反问**：信息不足时用 `interrupt` 挂起图，等用户回答后 `Command(resume=...)` 恢复。
- **证据核验**：由独立 Agent 逐条核验诊断结论是否被证据支撑（**证据 = 故障码查表结果 + RAG 片段**）。打回次数上限 `MAX_GROUNDING_RETRY`，防死循环。
- **结论兜底**：到达追问轮数上限时，提示词强制收敛 + 代码层兜底，保证 `diagnosis` 非空。

### 检索链路（`rag.py`）

```
query
  ├─ 故障码库：稠密(Milvus) + 稀疏(BM25)
  └─ 手册库：  稠密(Milvus) + 稀疏(BM25)
        ↓  库内 RRF 融合
        每库按配额保底取候选（fault_code 12 席 / manual 8 席）
        ↓  跨库加权 RRF 定序（故障码 1.5 > 手册 1.0）
        Cross-Encoder 精排 → Top-K
```

- **为什么分库**：故障码与手册混在同库时会互相竞争，实测 23 条故障码被 85 条手册完全淹没。
- **为什么还要配额**：只用加权会矫枉过正（手册一条都进不了重排器），配额保证两类知识都能被重排器看到，最终由 Cross-Encoder 按真实相关性裁决。
- **检索 query** 由 `品牌 + 症状 + 故障码` 拼接，故障码语料才能被精准命中。

### 可观测性与成本（`observability.py` / `cost.py` / `cache.py`）

- 所有 LLM 调用统一收口于 `llm.py`，自动产出 span（耗时 / token / 输入输出摘要 / 缓存命中）。
- 每次 `/api/diagnose` 请求开一条 trace，摘要随响应返回（`debug: true` 可看完整 span）。
- 模型按任务路由：`diagnose`/`safety_review`/`grounding_check` 走强模型，`summarize`/`classify` 走轻模型。
- 响应缓存仅在 `temperature ≈ 0` 时启用（避免固化随机采样），配置 `REDIS_URL` 自动切 Redis，不可用时静默回退内存。

## 环境变量

除基础的 LLM / 数据库配置外，以下为检索与成本控制相关项（均有默认值）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `RAG_MODE` | `hybrid` | `hybrid`（稠密+BM25+RRF+重排）/ `dense`（纯向量） |
| `RAG_RECALL_N` | `20` | 每路粗召回条数 |
| `RERANK_ENABLED` / `RERANK_MODEL` | `1` / `BAAI/bge-reranker-base` | 重排开关与模型 |
| `RAG_QUOTA` | `{"fault_code":12,"manual":8}` | 各知识库保底进入重排的候选数 |
| `RAG_WEIGHTS` | `{"fault_code":1.5,"manual":1.0}` | 加权 RRF 的各库权重 |
| `DEEPSEEK_MODEL_STRONG` / `_LIGHT` | 回退到 `DEEPSEEK_MODEL` | 模型路由档位 |
| `CACHE_ENABLED` / `CACHE_TTL` / `REDIS_URL` | `1` / `3600` / 空 | 响应缓存 |

## 排查

```powershell
python diagnose_rag.py      # 逐段排查 RAG 链路，哪一步挂了直接打 traceback
python verify_after_opt.py  # 验证 trace / 缓存 / 混合检索 / 证据核验
python -m eval.run_eval     # 跑评估集（需服务已启动）
```
