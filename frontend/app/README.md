# 前端（React + Vite + Tailwind）

技术栈：React 18 + Vite 5 + Tailwind CSS 3（PostCSS 方式）。

## 本机运行

```powershell
cd frontend/app
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

## npm 慢/失败时换国内镜像

```powershell
npm config set registry https://registry.npmmirror.com
```

然后再 `npm install`。

## 目录结构

```
src/
  main.jsx                  # 入口
  App.jsx                   # 主布局：Header + 左侧三卡片 + Chat
  api.js                    # 后端 API 封装（诊断 / 家电 / 历史）
  index.css                 # Tailwind 指令 + 全局样式
  data/mock.js              # 早期模拟数据，当前未使用
  components/
    Header.jsx              # 顶栏
    ApplianceList.jsx       # 我的家电（展开详情 / 加入 / 删除二次确认）
    HistoryList.jsx         # 维修历史（展开详情 / 删除二次确认）
    SafetyManual.jsx        # 通用安全手册（静态）
    Chat.jsx                # 提问交互区（核心：消息流 + 图片上传 + 多轮诊断）
```

## 后端对接

- `vite.config.js` 已配置 `/api` 代理到 `http://127.0.0.1:8000`（FastAPI）。
- `Chat.jsx` 通过 `api.js` 调 `POST /api/diagnose`：首轮返回 `need_info` 时保存 `thread_id`，后续用 `{thread_id, answer}` 继续，直到 `done`。
- `App.jsx` 启动时并行拉取家电名单与维修历史；新增/删除走对应 CRUD 接口。
