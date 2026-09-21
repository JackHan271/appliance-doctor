# 前端（React + Vite + Tailwind）

技术栈：React 18 + Vite 5 + Tailwind CSS 3（PostCSS 方式）。

## 本机运行

```powershell
cd C:\Users\ASUS\Desktop\appliance-doctor\frontend\app
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
  index.css                 # Tailwind 指令 + 全局样式
  data/mock.js              # 模拟数据（家电 / 历史）
  components/
    Header.jsx              # 顶栏
    ApplianceList.jsx       # 我的家电（展开详情 / 加入 / 删除二次确认）
    HistoryList.jsx         # 维修历史（展开详情 / 删除二次确认）
    SafetyManual.jsx        # 通用安全手册（静态）
    Chat.jsx                # 提问交互区（核心：消息流 + 图片上传 + mock 诊断引擎）
```

## 接真实后端（后续）

- `vite.config.js` 已配置 `/api` 代理到 `http://127.0.0.1:8000`（FastAPI）。
- `Chat.jsx` 里的 mock 诊断引擎（`REPORT` 工厂 + `runScenario` 场景判断）需要替换为对后端 `/diagnose` 的真实调用：文字/图片发送 → `POST /api/diagnose`，多轮追问时用返回的 `thread_id` 携带 `answer` 继续。
- `data/mock.js` 的家电/历史数据替换为对后端 CRUD 接口的请求。
