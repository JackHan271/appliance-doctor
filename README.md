# 家电医生 · Appliance Doctor

面向家庭用户的冰箱故障诊断 Web 应用：用文字或照片描述故障，经多 Agent 多轮诊断，输出带三级安全护栏的维修建议。

> ⚠️ 重要：本项目的维修建议仅供参考，不能替代专业检修。涉及高压电、压缩机、制冷剂、主控板、传感器、加热管的场景，请务必联系官方售后。

## 结构

- `frontend/app` - React 前端，四区域界面：家电名单 / 提问诊断 / 维修历史 / 安全手册
- `backend/app` - FastAPI 后端
- `backend/app/graph` - LangGraph 多 Agent 诊断图：诊断 / 反问 / 证据核验 / 安全审查
- `backend/app/tools` - 工具实现：查故障码 / 读铭牌 / 识别现象 / 查安全手册
- `backend/app/mcp_server.py` - MCP Server，暴露 4 个 Tools、3 个 Resources、2 个 Prompts
- `backend/app/rag.py` - 分库混合检索：稠密向量 + BM25 关键词，RRF 融合后重排
- `backend/app/memory.py` - 三层记忆的长期层，存跨会话的用户偏好与结论
- `backend/app/context.py` - 上下文工程：token 预算与滚动摘要
- `backend/app/observability.py` - trace 与 span 埋点
- `backend/app/cost.py` - 按任务路由模型与费用估算
- `backend/app/cache.py` - 响应缓存，内存与 Redis 自动降级
- `backend/ingest.py` - 统一语料入库：分库写入、中文过滤、幂等重建
- `backend/eval` - 评估集与 harness
- `backend/diagnose_rag.py` - RAG 链路逐段排查脚本
- `backend/check_services.py` - 一键体检，检查向量库与后端端口
- `data` - 故障码表、型号种子、手册语料
- `docs` - 需求、技术选型、设计规范、执行计划、数据策略

## 安装

需要 Python 3.12、Node.js，以及 PostgreSQL（建库 `appliance_doctor`）。

在 `backend` 目录建虚拟环境并安装依赖：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

再把 DeepSeek key 与数据库连接串填进 `backend/.env`，模板见 `backend/.env.example`。

## 运行

`backend` 下有两个一键启动脚本，双击即可，窗口标题会标注「请勿关闭」：

- `启动Milvus.bat` - 启动向量库，必须常开，关掉后检索即失效
- `启动后端.bat` - 启动 FastAPI 服务

也可以手动开三个终端：

```powershell
cd backend; .venv\Scripts\Activate.ps1
milvus-lite server --data-dir ./milvus_data --port 19530
```

```powershell
cd backend; .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

```powershell
cd frontend/app
npm run dev
```

首次运行需要先灌语料，把故障码与中文手册分别写入两个知识库：

```powershell
cd backend; .venv\Scripts\Activate.ps1
python ingest.py
```

浏览器打开 http://localhost:5173。重新灌库后，运行中的后端仍持有旧语料的关键词索引，重启服务或调用 `POST /api/admin/reindex` 刷新。

## 排查

- `python check_services.py` - 检查向量库与后端端口是否在监听
- `python diagnose_rag.py` - 逐段排查 RAG 链路，哪一步失败会直接打出 traceback
- `python verify_after_opt.py` - 验证 trace、缓存、混合检索与证据核验是否生效
- `GET /api/metrics` - 查看缓存命中率与各知识库的健康状态

## 技术要点

诊断图是一条带条件边和回退的状态机。诊断 Agent 信息不足时用 `interrupt` 反问用户，收敛后进入证据核验 Agent，核验不通过会打回重诊（最多一次，防死循环），通过后交给安全审查 Agent 独立复核，最后写入长期记忆。

三级安全护栏划分如下：绿色对应完全不打开盖板的面操作，可安全自修；黄色对应需要打开盖板或接触内部部件，必须先断电；红色对应传感器、电路、制冷剂、压缩机一类，只解释原因，不给拆机步骤。安全审查 Agent 独立于诊断 Agent，可主动升级等级。

检索链路分成两个知识库。故障码表是结构化高置信知识，手册是非结构化的补充材料；两者混在同一个库里会互相竞争，实测中 23 条故障码会被 85 条手册完全淹没。所以按库分别召回，再按配额保底与加权融合，最后统一交给重排模型裁决。

## 评估

评估集共 135 条用例，分三类来源：人工精写 35 条、从故障码表程序化生成 92 条、安全护栏 8 条。

运行 `python -m eval.run_eval` 复现。等级类指标在关闭响应缓存的条件下实测，避免缓存复用掩盖真实表现：

- red 档准确率：100%（100/100）
- 危险漏报：0
- 偏松：0
- 安全护栏通过率：100%（7/7）
- 整体安全等级准确率：100%（133/133）
- 诊断可用率：96.9%（123/127）

red 档指传感器、电路、制冷剂一类硬故障，属安全关键，判定稳定。green 与 yellow 的边界本身带有灰度，「擦门封算绿还是黄」这类判断会因批次不同而摆动，所以评估脚本分层输出，不把两档混成一个总分。

诊断可用率依赖「结论是否命中预期原因关键词」的匹配口径，关缓存实测时为 92.9%，修订关键词匹配后为 96.9%。剩余少数未命中的用例，是模型诊断表述较笼统，属真实的表述差异而非测量误差。

评估集同时充当回归基线：改动 Prompt、检索链路或模型后重跑，即可确认没有引入退化。

## 参与贡献

欢迎提 issue 或 pull request。新增故障码请直接改 `data/fault_codes/*.json`，然后运行 `python eval/gen_cases.py` 重新生成对应用例。

## 许可

仅用于学习与技术交流。故障码数据整理自公开维修资料；说明书语料版权归原厂商所有，不得用于商业分发。
