# Docker 一键部署

三个容器：PostgreSQL（数据库）、backend（FastAPI + 内嵌 Milvus Lite）、frontend（React build + nginx）。

## 前置：安装 Docker Desktop

1. 访问 https://www.docker.com/products/docker-desktop/ 下载 Windows 版。
2. 安装（需要 WSL2 或 Hyper-V，安装器会引导你开启）。
3. 装完启动 Docker Desktop，等右下角鲸鱼图标变绿（Docker 引擎运行中）。

## 配置 DeepSeek API Key

在项目根目录（`appliance-doctor/`）新建一个 `.env` 文件，内容一行：

```
DEEPSEEK_API_KEY=你的key
```

（docker-compose 会自动读这个文件，把 key 注入 backend 容器。）

## 一键启动

在项目根目录打开 PowerShell：

```powershell
docker compose up --build
```

首次会拉镜像 + 构建，比较久（几分钟）。等三个服务都起来后：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/health

## 停止 / 清理

```powershell
docker compose down          # 停止（保留数据）
docker compose down -v       # 停止并删除数据卷（清空数据库和向量库）
```

## 说明

- **数据持久化**：PostgreSQL 数据在 `pgdata` 卷、Milvus 向量数据在 `milvus_data` 卷，重启容器不丢。
- **RAG 语料**：Docker 版向量库默认为空，但诊断主流程（LLM + 故障码查表 + 安全护栏）不受影响；如需检索知识，下载说明书 PDF 后用 `docker cp` 放进 backend 容器，再 `docker exec backend python scripts/ingest_manuals.py` 入库。
- **端口**：5173（前端）、8000（后端）、5432（数据库，也映射到宿主机方便本地 psql 查看）。
