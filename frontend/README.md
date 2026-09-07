# 超星助手 (Chaoxing Assistant) — Electron + Vue3 前端

桌面端超星学习通课程自动化工具的前端，基于 **Electron + Vue 3 + TypeScript + Vite** 构建。

前端通过 Electron 主进程将操作转发给独立的 Python 后端（Playwright 浏览器自动化 + AI 答题）。纯浏览器环境下自动切换到 Mock 模式，无需后端即可开发调试 UI。

## 技术栈

| 层 | 技术 |
|---|------|
| 框架 | Vue 3.4 (Composition API, `<script setup>`) |
| 语言 | TypeScript 5（strict） |
| 构建 | Vite 5 |
| 状态管理 | Pinia 2（9 个 Store） |
| 路由 | Vue Router 4（hash 模式） |
| 桌面壳 | Electron 28 |
| 样式 | Scoped CSS + CSS 自定义属性（玻璃拟态，亮/暗双主题） |
| 类型检查 | vue-tsc 2.x |

## 快速开始

```bash
cd frontend
npm install

# Web 开发模式（Mock 数据，无需后端，端口 5173）
npm run dev

# Electron 开发模式（真实 IPC + Python 后端）
npm run dev:electron

# Electron 模式前置：Python 3.10+（含 openai，见 ../backend/requirements.txt）
# 与全局 playwright-cli；可在「系统设置 → Python 路径」指定解释器（留空用 PATH）。

# 仅构建 Web 产物 (dist/)
npm run build:web

# 仅重建 Electron 主进程 / preload (dist-electron/) —— 改过 electron/* 后必须执行
npx vite build --mode electron

# 构建桌面应用 (dist/ + electron-builder)
npm run build

# 预览已构建的 Web 产物
npm run preview

# 类型检查（渲染进程 + Node 侧分两次执行）
npm run typecheck
```

> Mock 模式：`createApiClient()` 检测不到 `window.electronAPI` 时返回 `MockApiClient`，使用内存模拟数据，任务启动后通过 `setTimeout` tick 循环自动推进阶段、泳道进度与日志，不发起任何网络请求。

> 注意：`npm run build:web` 只构建渲染进程（`dist/`），**不会**重建 `dist-electron/`。
> 修改 `electron/` 主进程代码（IPC、状态机、账号处理等）后，需额外执行
> `npx vite build --mode electron`（或直接 `npm run build`），否则界面运行的是旧主进程。

## NPM 脚本一览

| 脚本 | 作用 |
|------|------|
| `dev` | Vite 开发服务器（Web / Mock 模式） |
| `dev:electron` | Vite + Electron（`--mode electron`） |
| `build:web` | 仅 `vite build`，输出到 `dist/` |
| `npx vite build --mode electron` | 仅重建 Electron 主进程 / preload 到 `dist-electron/` |
| `build` | `vite build && electron-builder`，打包桌面应用 |
| `preview` | 预览 `dist/` 产物 |
| `typecheck` | `vue-tsc -p tsconfig.json` + `vue-tsc -p tsconfig.node.json`，均 `--noEmit` |

## 项目结构

```
frontend/
├── package.json
├── vite.config.ts
├── index.html                      # 应用入口（挂载 #app，加载 src/main.ts）
├── tsconfig.json                   # 渲染进程配置（DOM lib，src/**）
├── tsconfig.node.json              # Node 侧配置（node types，vite.config + electron/**）
├── src/                            # Vue3 渲染进程
│   ├── main.ts                     # Vue 应用入口
│   ├── env.d.ts                    # 环境/类型声明
│   ├── app/
│   │   ├── App.vue                 # 根布局（侧边栏 + router-view + 日志控制台）
    │   │   └── stores/                 # Pinia 状态管理（9 个）
    │   │       ├── account.store.ts    # 账号列表与选择
    │   │       ├── attention.store.ts  # 工单（去重 + 上限 200）
    │   │       ├── campaign.store.ts   # 任务配置（目标/策略/模式 + 预估）
    │   │       ├── captcha.store.ts    # 验证码队列（人工介入弹窗）
    │   │       ├── course.store.ts     # 课程（按账号缓存、扫描、选择同步）
    │   │       ├── execution.store.ts  # 任务执行（事件监听、计时器、泳道控制）
    │   │       ├── log.store.ts        # 日志缓冲（上限 500）
    │   │       ├── memory.store.ts     # 内存计划 / MEMORY 事件（预算仪表）
    │   │       └── settings.store.ts   # 系统设置（localStorage + 防抖同步）
│   ├── router/
│   │   └── index.ts                # 路由配置（5 条 hash 路由 + lazy load）
│   ├── shared/
│   │   ├── lib/                    # 适配层、类型、工具
│   │   │   ├── types.ts            # 渲染进程类型 + ChaoxingApi 接口
│   │   │   ├── apiClient.ts        # API 客户端工厂（环境检测）
│   │   │   ├── ipcClient.ts        # ElectronApiClient（类型映射）
│   │   │   ├── mockClient.ts       # MockApiClient（含模拟任务循环）
│   │   │   ├── mockData.ts         # Mock 数据生成器
│   │   │   ├── constants.ts        # OBJECTIVES / STRATEGIES / MODES / DEFAULT_SETTINGS
│   │   │   ├── designTokens.ts     # 亮/暗主题 CSS 自定义属性
│   │   │   └── formatDuration.ts   # 毫秒 → "Xh Ym Zs"
│   │   └── ui/                     # 可复用 UI 组件（PillButton / Chip / ProgressBar 等）
│   └── views/                      # 页面组件
│       ├── DashboardView.vue
│       ├── CourseAtlasView.vue
│       ├── ExecutionStudioView.vue
│       ├── AttentionQueueView.vue
│       └── SettingsView.vue
└── electron/                       # Electron 主进程
    ├── main.ts                     # 窗口创建、IPC 注册、生命周期、Chromium 清理
    ├── preload.ts                  # contextBridge（window.electronAPI）
    ├── types.ts                    # IPC 类型 + IPC_CHANNELS 常量
    ├── ipc/
    │   ├── job.handler.ts          # 任务 IPC（RAM 检查、限流、PythonBridge 绑定）
    │   ├── course.handler.ts       # 课程 IPC（读取 Python 发现状态，真实后端）
    │   ├── status.handler.ts       # 账号/状态/设置/工单 IPC（accounts:status、tickets 仍为桩）
    │   └── balance.handler.ts      # 余额 IPC（spawn chaoxing-backend 跑 chaoxing.balance，§4.7）
    └── python/
        └── pythonBridge.ts         # Python 子进程桥接（spawn、NDJSON 解析、生命周期）
```

## 页面路由

默认重定向 `/` → `/dashboard`。

| 路由 | 组件 | 功能 |
|------|------|------|
| `/dashboard` | DashboardView | 概览仪表盘（统计、账号矩阵、资源监控、时间线） |
| `/course-atlas` | CourseAtlasView | 账号面板 + 课程网格，扫描与任务启动 |
| `/execution-studio` | ExecutionStudioView | 实时执行监控（状态横幅、阶段步进、账号泳道） |
| `/attention-queue` | AttentionQueueView | 工单分级、结果预测、操作日志 Feed |
| `/settings` | SettingsView | AI 推理 / 账号管理 / 浏览器与系统 / 运行与内存 / 主题 |

> 任务从 **课程总览 (`/course-atlas`)** 选择账号与课程后启动，没有独立的「任务规划」页面。

## 执行模式 (MODES)

启动任务时选择执行模式，前端 `ModeType`（6 种）由 `ElectronApiClient` 映射为后端 3 值 `mode`：

| 前端 ModeType | 后端 mode | 说明 |
|---------------|-----------|------|
| `course-scan` | `scan_only` | 课程扫描（只读） |
| `section-scan` | `scan_only` | 章节扫描（只读） |
| `dry-run` | `scan_only` | 模拟运行（只读） |
| `batch-exec` | `solve_only` | 批量执行 |
| `single-exec` | `full` | 单任务执行 |
| `full-auto` | `full` | 全自动模式 |

> 反向映射是有损的：`scan_only → course-scan`、`solve_only → batch-exec`、`full → full-auto`，`section-scan / dry-run / single-exec` 无法回程还原（仅作 `getJobStatus` 缺省回退用）。

## 设计系统

CSS 自定义属性驱动，支持亮/暗双主题（设置 → 主题切换）：

- **亮色**：暖色调玻璃拟态（teal / orange / gold / green，奶油底）
- **暗色**：深蓝海军色（indigo / amber / green / red，深底）

## 前后端通信

完整契约见 **[../docs/design/api.md](../docs/design/api.md)**，分三层：

1. **Layer 1** — `ChaoxingApi` TypeScript 接口（Store 消费层，字符串 ID、UI 形态类型）
2. **Layer 2** — Electron IPC 协议（Renderer ↔ Main，数字 ID、后端形态类型，28 个 invoke 通道 + 8 个事件通道）
3. **Layer 3** — Python 子进程 stdin/stdout NDJSON 协议（控制信号 `PAUSE`/`RESUME`/`STOP`，事件 `PROGRESS`/`PHASE`/`LOG`/`TICKET`/`RESULT`/`ERROR`/`MEMORY`/`DONE`）

`ElectronApiClient`（`ipcClient.ts`）是两套类型系统之间的映射层：账号 ID `string ↔ number`、Course/Settings/Ticket 形态转换、模式与 AI 提供方映射、事件重整。`MockApiClient` 直接实现 Layer 1，不经过 IPC。

## 已知约束

- **类型检查**：使用 `vue-tsc 2.x`（兼容 Node 24 + TypeScript 5.9）。旧版 `vue-tsc 1.8` 在 Node 24 下会因补丁 TS 内部字符串失败而崩溃，已升级。`typecheck` 拆成渲染进程（`tsconfig.json`，DOM lib）与 Node 侧（`tsconfig.node.json`，node types）两次执行，避免 DOM/Node 类型冲突与 composite 项目引用问题。
- **逐账号运行时控制**：Mock 模式完整支持选中账号的 暂停/恢复/停止；Electron 模式下，当选中集合等于任务全部账号时降级为全局控制，**真子集会显式抛错**（当前 Python 后端不支持逐账号控制）。详见 API 文档第 7 节。
- **数据接入**：`job:*`、`courses:*`、`accounts:*`、`balance:query` 与全部事件通道已接真实后端；`tickets:list` 与 `accounts:status` 仍为桩数据（真实工单与账号状态走事件流）。

## 后端仓库

后端位于同仓库 `backend/`。接入只需关注 Layer 3：实现 `--job-id / --accounts / --mode / --courses / --max-concurrent / --budget-gb / --system-limit-gb / --per-account-estimate-gb` 命令行入口，stdout 输出 NDJSON 事件，stdin 读取控制信号。
