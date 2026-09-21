# 后端骨架（Phase 2）

技术栈：FastAPI + LangGraph + Claude + Milvus（Lite）+ 可配置 Embedding + MCP。

## 目录结构

```
backend/
  app/
    config.py          # 配置（环境变量）
    llm.py             # Claude 接入（文本 + 视觉）
    embedding.py       # Embedding 可配置抽象（bge/dashscope/openai）
    vectordb.py        # Milvus 接入（Lite）
    tools/
      fault_code.py    # 查故障码工具（读 data/fault_codes/*.json）
    graph/
      state.py         # LangGraph 诊断状态定义（图组装待下一版）
    main.py            # FastAPI 入口（health + 查故障码演示端点）
```

## 本机运行（Windows PowerShell）

### 前置：Python ≥ 3.10

### 步骤 A：最小验证（快速，只装 fastapi + uvicorn，不碰 torch）

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # 若报"禁止运行脚本"，改用下一行
.venv\Scripts\activate.bat        # 或：Set-ExecutionPolicy -Scope Process Bypass 后重试上一行
pip install fastapi "uvicorn[standard]"
uvicorn app.main:app --reload
```

浏览器验证：
- `http://127.0.0.1:8000/health` → 应返回 `{"status":"ok"}`
- `http://127.0.0.1:8000/tools/fault-code?brand=%E6%B5%B7%E5%B0%94&category=washing_machine&code=E1&load_type=top_load` → 应返回海尔 E1 的完整结果

### 步骤 B：完整验证（装全套，含 torch，耗时较长）

```powershell
pip install -r requirements.txt   # sentence-transformers 会拉 torch，约 2GB，属正常
python -c "from app import llm, embedding, vectordb; print('imports ok')"
```

### 步骤 C：带 API 的端到端（需 .env 配 key）

```powershell
Copy-Item .env.example .env       # 填入 ANTHROPIC_API_KEY
```

## 说明

- 本骨架在协作环境（沙箱）不可用，未经过运行验证；本机跑如有报错，贴回我来改。
- `CLAUDE_MODEL` 请按你的 API 可用模型名修改（占位为 `claude-sonnet-4-5`）。
- Milvus 用 Lite 模式（本地 `milvus_lite.db`），无需单独起服务。
- LangGraph 图组装（诊断 Agent + 安全审查 Agent 的边与节点）在下一步实现。
