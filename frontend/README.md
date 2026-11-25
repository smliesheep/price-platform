# 价格监控平台 · 前端

Kubernetes 云原生 RPA 价格监控平台的前端控制台，基于 **Vue 3 + Vite + TypeScript**，提供商品监控、目标价曲线、采集计划、执行记录与系统状态查看。

## 技术栈

| 能力 | 依赖 |
| --- | --- |
| 框架 | Vue 3（`<script setup>` + Composition API） |
| 构建 | Vite 6 + TypeScript |
| 路由 / 状态 | Vue Router 4 + Pinia 2 |
| UI | Element Plus（全量引入，中文 locale）+ 本地图标库 |
| 图表 | ECharts 5（折线图、目标价 markLine） |
| 请求 | axios（统一注入 Bearer token 与 `X-Trace-Id`） |

## 环境要求

- Node.js 24（开发机使用 v24.14.1 验证）
- npm，默认 registry 为 <https://registry.npmmirror.com>
- 后端 API 运行在 `http://127.0.0.1:8000`（开发环境由 Vite 代理 `/api`）

## 开发

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5173>。开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`，因此本地需要先启动后端。

默认账号：`admin` / `admin123`。

## 构建与检查

```bash
npm run typecheck   # vue-tsc --noEmit，仅类型检查
npm run build       # 类型检查 + 生产构建，产物在 dist/
npm run preview     # 本地预览 dist
```

`npm run build` 会执行 `vue-tsc --noEmit && vite build`，任何 TypeScript 错误都会导致构建失败。

## Docker

```bash
# 在 frontend 目录构建镜像
docker build -t price-monitor-frontend .

# 运行时需要与后端 api 服务处于同一 Docker 网络（nginx.conf 中反代到 http://api:8000）
docker run --rm -p 8080:80 --network <backend-network> price-monitor-frontend
```

镜像为多阶段构建：`node:24-alpine` 负责构建，`nginx:1.27-alpine` 负责托管 `dist`。

## 目录结构

```text
frontend/
├── Dockerfile
├── nginx.conf              # SPA fallback + /api 反代 + gzip
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── public/
│   └── favicon.svg
└── src/
    ├── api/                # axios 实例与按域拆分的 API 封装
    ├── components/         # 布局、价格图、队列水位、执行抽屉等
    ├── composables/        # usePolling / useTheme
    ├── router/             # 路由与登录守卫
    ├── stores/             # Pinia auth store
    ├── styles/             # 主题变量与全局样式
    ├── utils/              # 格式化、localStorage 封装
    ├── views/              # 登录、概览、商品、详情、任务、记录、系统
    ├── App.vue
    └── main.ts
```

## 页面

| 路由 | 说明 |
| --- | --- |
| `/login` | 登录页，登录后将 token 写入 localStorage 并跳转 |
| `/overview` | 4 个指标卡、队列水位、Top 错误、最近失败记录，15s 轮询 |
| `/products` | 商品筛选、分页、启停、立即采集、删除、新增商品对话框 |
| `/products/:id` | 商品信息、目标价编辑、ECharts 价格曲线、执行记录、计划配置 |
| `/tasks` | 任务列表、暂停/恢复/立即执行、间隔与超时编辑，30s 轮询 |
| `/runs` | 多条件筛选、分页、执行详情 Drawer（trace_id / 错误信息） |
| `/system` | Worker 心跳、Redis Stream 队列、版本信息，10s 轮询 |

## 实现说明

- 所有请求经 `src/api/http.ts` 的 axios 实例发出：自动携带 `Authorization: Bearer <token>` 与随机 16 位 hex 的 `X-Trace-Id`，统一拆封 `{ code, message, data, trace_id }`，`code !== 0` 或 HTTP 错误会抛出 `ApiError` 并通过 `ElMessage` 提示。
- HTTP 401 会清除本地 token、记录回跳地址并跳转 `/login`；登录页通过会话级提示展示“登录状态已失效”。
- 轮询统一使用 `usePolling(fn, intervalMs)`：页面隐藏时暂停定时器，重新可见时立即刷新，组件卸载时清理监听。
- 金额统一保留两位小数（`formatMoney`），时间按浏览器本地时区格式化为 `YYYY-MM-DD HH:mm:ss`（`formatDateTime`）。
- 浅色为默认主题，顶栏可切换深色；主题偏好存入 localStorage，图表会跟随主题重绘。
- 未使用任何外网 CDN 资源，字体使用系统字体，图标来自 `@element-plus/icons-vue`。
- Element Plus 采用全量引入，未做按需加载；ECharts 与 Element Plus 在构建时拆分为独立 chunk，避免首屏体积互相绑定。
