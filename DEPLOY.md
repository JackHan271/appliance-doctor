# Docker 一键部署

五个服务：PostgreSQL（业务数据库）、Milvus（向量库，milvus-lite server）、Redis Stack（缓存 + 会话状态持久化）、backend（FastAPI + LangGraph）、frontend（React build + nginx）。

## 前置

1. 安装并启动 Docker Desktop（右下角鲸鱼图标变绿）。
2. 在项目根目录（`appliance-doctor/`）建一个 `.env` 文件，内容一行：

```
DEEPSEEK_API_KEY=你的key
```

docker-compose 会自动读这个文件，把 key 注入 backend 容器。

## 一键启动

在项目根目录打开 PowerShell：

```powershell
docker compose up --build
```

首次会拉镜像 + 构建 + 下载依赖，比较久（几分钟到十几分钟）。backend 首次启动还会后台下载 BGE embedding 与重排模型（约 1.5GB，走 HF 镜像），属正常现象。

启动完成后：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/health
- 运行指标（缓存后端、各知识库健康）：http://localhost:8000/api/metrics

## 灌语料

Docker 镜像里不含原始手册 PDF（版权原因，`.dockerignore` 已排除），所以容器内只能灌故障码知识：

```powershell
docker exec -it $(docker ps -qf "name=backend") python ingest.py --no-manuals
```

或先找到 backend 容器名：

```powershell
docker ps
```

然后 `docker exec -it <容器名> python ingest.py --no-manuals`。

重新入库后，调用 `POST /api/admin/reindex` 刷新关键词索引，无需重启容器：

```powershell
curl.exe -X POST http://localhost:8000/api/admin/reindex
```

## 验证会话持久化

Redis 承担会话状态持久化：发一次诊断（返回 need_info 拿 thread_id），重启 backend 容器后用同一 thread_id 继续，应能接着上一轮。

## 停止 / 清理

```powershell
docker compose down          # 停止（保留数据）
docker compose down -v       # 停止并删除数据卷（清空数据库、向量库、Redis）
```

## 端口

| 端口 | 服务 |
|------|------|
| 5173 | 前端 |
| 8000 | 后端 |
| 5432 | PostgreSQL（映射到宿主机，方便本地 psql） |
| 19530 | Milvus |
| 6379 | Redis |

## 生产注意

- `milvus-lite server` 适合开发与中小规模演示；数据量大或需高可用时，替换为 `milvusdb/milvus` standalone 或 Zilliz Cloud，代码侧只需改 `MILVUS_URI`。
- `postgres:postgres` 是默认口令，部署到公网务必修改。
