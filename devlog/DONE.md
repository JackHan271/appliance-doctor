# 已完成事项（DONE）

> 按时间倒序记录。

- [x] 2026-09-21 简历包装完成：README.md（含 Mermaid 架构图）+ docs/06-简历与面试.md（简历 bullets + 面试问答要点 + 演示建议）
- [x] 2026-09-21 评估集扩充至 35 例（red19/yellow10/green6，三品牌），指标定稿：安全等级准确率约 90%、危险漏报率 0（多次运行稳定）
- [x] 2026-09-20 数据持久化（PostgreSQL + SQLAlchemy：家电名单/维修历史 CRUD 接口 + 前端接后端拉取/增删）；图片识别接入诊断主流程
- [x] 2026-09-20 Docker 一键部署（docker-compose：postgres + backend[内嵌 milvus-lite] + frontend[nginx]，含 Dockerfile/nginx.conf/.dockerignore/DEPLOY.md）
- [x] 2026-09-20 前后端打通 + 图片识别接入诊断主流程（后端 /api 前缀路由、state 加 image 字段、diagnose 节点用 chat_with_image 视觉模型、前端传 base64）；修复 diagnosis 空值兜底文案
- [x] 2026-09-19 Phase 5 前端正式版（React 18 + Vite 5 + Tailwind 3，frontend/app 共 15 文件：Header/家电名单/历史/安全手册/提问交互区；淡蓝主题 + 绿黄红安全色；图片上传 + 增删二次确认；mock 数据 + /api 代理预留接后端）
- [x] 2026-09-19 Phase 5 前端 mock demo（frontend/demo.html 单文件：四区域淡蓝界面 + 多轮诊断交互 + 绿黄红安全等级 + 铭牌式诊断报告卡，数据全部模拟）；正式前端定 React+Vite+Tailwind
- [x] 2026-09-19 RAG 冰箱语料入库完成（210 片段：西门子中文说明书 3 份 + 美的维修手册 1 份）；评估可用率 66.7%→73.3%，安全指标稳定（危险漏报 0、偏松 0）；修复 too_many_pings（init 后移 + 分批 insert）
- [x] 2026-09-19 评估集冰箱版跑通：准确率 93.3%（14/15）、危险漏报 0；prompt 强化"报警/提示类先自查"生效（E6/H/L 修正）
- [x] 2026-09-19 清理无关数据：删除 gree.json、manuals/README 改为冰箱三品牌；新增 reset_rag.py 用于清空 Milvus 旧洗衣机语料
- [x] 2026-09-19 方向收敛：品类最终确定为只做冰箱，品牌海尔/美的/西门子；故障码数据（23 条）、诊断 prompt、评估集（15 用例）全部更新为冰箱
- [x] 2026-09-19 Phase 3 多轮诊断端到端验证通过：模糊症状 → Agent 追问故障码 → 回答 E1 → 查表+LLM 诊断 → 安全审查判 yellow（并提示涉排水泵转 red）；interrupt/resume 全链路正常
- [x] 2026-09-19 Phase 3 多轮诊断实现：诊断图改为 diagnose → ask_user(interrupt 反问) → 循环 → safety_review，加轮数上限与问答历史；/diagnose 支持 thread_id + Command(resume) 恢复；沙箱语法验证通过，待本机端到端验证
- [x] 2026-09-19 MCP server 验证通过（mcp 1.30.0；4 工具列出 + fault_code 调用成功）；根因 mcp 2.x 已改 API（FastMCP→MCPServer），requirements 锁 mcp<2
- [x] 2026-09-19 MCP 工具集代码完成（read_nameplate / identify_symptom / search_safety_manual 纯函数 + FastMCP server 组装 + requirements 加 mcp 包）；沙箱语法 + parse_json 验证通过，待本机装 mcp 跑通
- [x] 2026-09-19 DeepSeek 视觉模型 deepseek-v4-flash-vision-exp 调通（llm.py chat_with_image 支持 deepseek 视觉，base64 内联）；照片提问的视觉前置就绪
- [x] 2026-09-19 RAG 检索链路打通（Milvus gRPC server 模式 + BGE embedding + 62 条故障码语料入库 + 诊断图接入检索）；检索验证准确，诊断可引用检索知识（如 E1 故障码）
- [x] 2026-09-19 LangGraph 诊断图单轮版（诊断 Agent → 安全审查 Agent，三级护栏）+ /diagnose 路由；green/yellow/red 三级全部验证通过；llm.py 加 temperature=0 保证分级确定性
- [x] 2026-09-19 LLM 层接入 DeepSeek（OpenAI 兼容接口，国内直连）并验证通过；llm.py 改为 deepseek + anthropic 双 provider（默认 deepseek）
- [x] 2026-09-19 本机环境搭建（Windows 原生 + Python 3.12 + venv + 清华镜像装齐依赖）+ 骨架验证通过（uvicorn 起服务、/health、/tools/fault-code 正常）
- [x] 2026-09-18 Phase 2 代码骨架：FastAPI + Claude（文本/视觉）+ Embedding 可配置 + Milvus + 查故障码工具 + LangGraph 状态
- [x] 2026-09-18 扩充故障码数据（海尔/美的/西门子，波轮+滚筒分层）；格力降为后备品牌
- [x] 2026-09-18 Phase 1 数据层完成：数据目录 + JSON schema + 四大品牌故障码 + 型号种子 + 手册采集脚本
- [x] 2026-09-18 锁定技术选型：PostgreSQL、Claude（LLM 文本 + 视觉）、BGE（Embedding）
- [x] 2026-09-18 确认 MVP 品牌名单（海尔/美的/西门子/格力）与选型（Milvus/FastAPI/Tailwind）
- [x] 2026-09-18 建立项目目录结构、docs 标准文件、devlog 日志、CLAUDE.md
- [x] 2026-09-18 确立技术路线（调用 LLM + RAG + 工具 + 多 Agent，不微调）
- [x] 2026-09-18 需求整理与四大关键决策拍板（Web 应用 / 三级安全护栏 / 3-4 品牌 MVP / 照片=现象+铭牌）
