# JLU Autonomous

吉林大学网课多平台自动学习助手。桌面端前端 (Electron + Vue 3) 驱动 Python 后端 (Playwright 浏览器自动化 + AI 答题) 完成课程学习、章节处理与测验答题。

> **本仓库由 [Chaoxing_auto](https://github.com/Joelin-CN/Chaoxing_auto) 迁移而来**（迁移基线 2026-08-27，未携带旧提交历史），并在此基线上向多平台演进。

## 平台支持

| 平台 | 状态 | 说明 |
|------|------|------|
| 超星学习通（含 OUC 开放大学） | ✅ 已支持 | 现有全部功能：课程扫描、章节处理、AI 测验答题、多账号并发 |
| 智慧树 (zhihuishu.com) | 🚧 规划中 | 目标：同级别自动化能力；路线图与调研骨架见 [docs/roadmap/zhihuishu.md](docs/roadmap/zhihuishu.md) |

## 项目结构

```text
JLU_Autonomous/
├── frontend/     # Electron + Vue 3 桌面端（electron/ 主进程 + src/ 渲染进程）
├── backend/      # Python 后端（chaoxing/ 包 + scripts/ + tests/ + CLI）
├── data/         # 运行时数据（凭据/浏览器档案/输出/日志，git 忽略）
├── references/   # 第三方参考脚本（git 忽略，仅索引）
├── docs/         # 文档中心（standards / roadmap / design / changelog / reports / validation / logs）
├── README.md / CONTRIBUTING.md / SECURITY.md / LICENSE / AGENTS.md
└── .github/      # CI 工作流 / Issue 与 PR 模板 / CODEOWNERS
```

> Monorepo：前端在 `frontend/`，后端在 `backend/`。前端在纯浏览器环境下自动切换 Mock 模式，无需后端即可开发调试 UI。后端整合细节见 **[docs/design/integration.md](docs/design/integration.md)**。

## 协作

本仓库由双管理者（[@Joelin-CN](https://github.com/Joelin-CN) / [@Arthur-Pendrag0n](https://github.com/Arthur-Pendrag0n)）异步维护：

- 开发协作（分支 / PR / 提交约定）见 **[CONTRIBUTING.md](CONTRIBUTING.md)**；
- 目录与文件规范见 [docs/standards/directory.md](docs/standards/directory.md) 与 [docs/standards/documents.md](docs/standards/documents.md)；
- 「刷课需求」通过 GitHub Issue 提交与认领（模板见 `.github/ISSUE_TEMPLATE/`）。

> **声明**：本项目仅供个人学习与技术研究交流，请勿用于任何商业用途或违反平台条款的场景，使用产生的一切后果由使用者自行承担。

## 架构总览

```
┌─────────────────────────────────────────────┐
│            Vue 3 前端 (Renderer)             │
│   Views / Components ←→ Pinia Stores (9)     │
│              ChaoxingApi (interface)         │
│         ├── ElectronApiClient (生产)         │
│         └── MockApiClient     (开发)         │
└───────────────────────┬─────────────────────┘
                        │ window.electronAPI (contextBridge / IPC)
┌───────────────────────▼─────────────────────┐
│             Electron Main Process            │
│   IPC Handlers (job / course / status)       │
│              ←→ PythonBridge (spawn)          │
│   + RAM 安全检查  + 500ms 限流                │
└───────────────────────┬─────────────────────┘
                        │ stdin 信号 / stdout NDJSON
┌───────────────────────▼─────────────────────┐
│             Python 后端 (子进程)             │
│   python -m chaoxing.api  (backend/)         │
│   + Playwright 封装 + AI 答题 (Doubao API)      │
└─────────────────────────────────────────────┘
```

- **命令流**：Vue Store → ElectronApiClient → IPC invoke → Main Handler → PythonBridge → Python 子进程
- **事件流**：Python 子进程 → stdout NDJSON → PythonBridge 解析 → IPC push → ElectronApiClient 回调 → Pinia Store

## 快速开始

```bash
cd frontend
npm install

# Web 开发模式（Mock 数据，无需后端）
npm run dev

# Electron 开发模式（真实 IPC + Python 后端）
npm run dev:electron

# 仅构建 Web 产物
npm run build:web

# 构建桌面应用
npm run build

# 类型检查
npm run typecheck
```

详细脚本与目录说明见 **[frontend/README.md](frontend/README.md)**。

## 前置依赖

桌面端不打包 Python / Node / Chrome —— 这些需在目标机器自行安装：

| 依赖 | 要求 | 说明 |
|------|------|------|
| **Python** | 3.10+ | 推荐 conda 环境 `chaoxing-backend`（`conda activate chaoxing-backend`）；也可在「系统设置 → Python 路径」指定其他解释器 |
| **Python 依赖** | `pip install -r backend/requirements.txt` | Playwright 封装、AI 答题等 |
| **Node.js** | 18+ | 仅开发 / 打包需要 |
| **playwright-cli** | `npm i -g playwright-cli` | 后端通过它驱动浏览器；须在 PATH |
| **Chrome** | 已安装 | Playwright 以 `--browser=chrome` 持久化模式启动 |
| **余额查询（可选）** | `pip install volcengine-python-sdk` | 已预装在 `chaoxing-backend` 环境；如用其他解释器，设环境变量 `CHAOXING_BALANCE_PYTHON` 指向它 |

**凭据文件**（放在 `data/passwords/`，**git 忽略、不随安装包分发**，需自行创建）：

| 文件 | 内容 |
|------|------|
| `chaoxing.txt` | 超星账号密码 |
| `doubao.txt` | `ARK_API_KEY="..."`（豆包 Ark 推理密钥，用于 AI 答题） |
| `volc_billing.txt` | `VOLC_ACCESS_KEY="..."` 与 `VOLC_SECRET_KEY="..."`（火山引擎 AK/SK，仅余额查询需要） |

> 打包后配置与只读资产播种到可写工作区（`%APPDATA%/超星助手/workspace/`），凭据/浏览器档案/日志等运行时数据落在 `%APPDATA%/超星助手/data/`，首启自动建目录，不会覆盖你已存在的文件。

## 打包与分发

```bash
cd frontend
npm install
npm run build        # vite build + electron-builder
```

产物在 `frontend/release/`（Windows NSIS 安装包）。打包仅含 Electron 应用 + 只读的 `backend/` 代码（白名单：`chaoxing/` 包、`scripts/` 只读资产、`chaoxing_config.json`、`requirements.txt`；`passwords/`、`chrome-profiles/` 等敏感/运行时目录**绝不入包**）；Python 运行时与上述依赖仍需目标机器自备。当前只产出 Windows 目标。

## 技术栈

- **Vue 3.4** + Composition API + `<script setup>`
- **Vue Router 4**（hash 模式）
- **Pinia 2**（9 个 Store）
- **TypeScript 5**（strict）+ **vue-tsc 2.x** 类型检查
- **Vite 5** 构建
- **Electron 28** 桌面壳

## 页面路由

默认重定向 `/` → `/dashboard`。

| 路由 | 视图 | 功能 |
|------|------|------|
| `/dashboard` | 仪表盘 | 统计卡片、账号矩阵、资源监控、时间线 |
| `/course-atlas` | 课程总览 | 账号面板 + 课程网格，扫描与任务启动 |
| `/execution-studio` | 执行监控 | 状态横幅、阶段步进器、账号泳道 |
| `/attention-queue` | 关注队列 | 工单分级、结果预测、操作日志 Feed |
| `/settings` | 系统设置 | AI 推理、账号管理、浏览器与系统、运行与内存、主题 |

## 前后端通信契约

完整定义见 **[docs/design/api.md](docs/design/api.md)**，分三层。

### Layer 1 — `ChaoxingApi` 接口（Store 层）

字符串 ID、UI 形态类型。`ElectronApiClient` 与 `MockApiClient` 都实现此接口。核心方法：`startJob` / `pauseJob` / `resumeJob` / `stopJob` / `pauseSelected` / `resumeSelected` / `stopSelected` / `getJobStatus` / `scanCourses` / `getCourses` / `getAccounts` / `getAccountStatus` / `getSettings` / `setSettings` / `getTickets` / `resolveTicket` / `resolveCaptcha` / `getBalance` / `getSystemResources` / `getMemoryPlan` / `getAiStatus` / `setAiConfig` / `testAi` / `addAccount` / `editAccount` / `removeAccount` / `openFilePicker` / `getAccountsDefaultPath` + 事件订阅 `onProgress` / `onPhaseChange` / `onLog` / `onTicket` / `onCompleted` / `onError` / `onResult` / `onMemory`。

### Layer 2 — Electron IPC 协议

数字 ID、后端形态类型。28 个 invoke 通道 + 8 个事件通道：

**Renderer → Main (invoke)**

| Channel | Payload | Response |
|---------|---------|----------|
| `job:start` | `{ accountIds: number[], courseIds?, mode? }` | `{ jobId }` |
| `job:pause` / `job:resume` / `job:stop` | `jobId` | void |
| `job:pause-selected` / `job:resume-selected` / `job:stop-selected` | `{ jobId, accountIds }` | void（真子集抛错） |
| `job:status` | `jobId` | `JobStatus` |
| `courses:scan` | `{ accountIds, courseIds? }` | `Course[]` |
| `courses:list` | `accountId` | `Course[]` |
| `accounts:list` | — | `Account[]` |
| `accounts:status` | `accountId` | `AccountStatus` |
| `settings:get` / `backend-settings:get` | — | `Settings` |
| `settings:set` / `backend-settings:set` | `Partial<Settings>` | void |
| `tickets:list` | — | `Ticket[]` |
| `tickets:resolve` | `ticketId, resolution` | void |
| `job:resolve-ticket` | `{ ticketId, accountId, answer? \| action:'skip' }` | void（验证码回传，转 stdin） |
| `balance:query` | — | `BalanceResult`（余额查询，§4.7） |
| `ai:status` / `ai:set` / `ai:test` | `{ apiKey?, model }` | AI 配置状态 / 保存 / 连通性测试 |
| `accounts:add` / `accounts:edit` / `accounts:remove` | 账号载荷 | void（原子写当前账号文件） |
| `accounts:default-path` | — | 默认账号文件绝对路径 |
| `memory:plan` | — | 空闲时按当前机器状态计算的并发计划 |
| `system:resources` | — | 实时系统资源（RAM / CPU / 运行时长） |
| `dialog:open-file` | — | 文件选择器结果（账号文件） |

**Main → Renderer (event)**：`on-progress` / `on-phase-change` / `on-log` / `on-ticket` / `on-completed` / `on-error` / `on-result` / `on-memory`，载荷为对应的 `Python*Event` 原始对象。

### Layer 3 — Python 子进程协议

**命令行入口**（`python -m chaoxing.api`，cwd = `backend/`）：

```
python -m chaoxing.api --job-id <id> --accounts <csv> --mode <full|scan_only|solve_only> [--courses <csv>] [--grade-only] [--content-only] [--max-concurrent <n>] [--budget-gb <gb>] [--system-limit-gb <gb>] [--per-account-estimate-gb <gb>]
```

**stdin 控制信号**（逐行）：`PAUSE\n` / `RESUME\n` / `STOP\n`

**stdout 事件**（NDJSON，每行一个 JSON 对象，含 `type` 判别字段）：

```json
{"type":"PROGRESS","jobId":"...","percent":45,"message":"...","phase":"solve_quiz","phaseIndex":3}
{"type":"PHASE","jobId":"...","phase":"solve_quiz","phaseIndex":3,"fromPhase":"process_sections"}
{"type":"LOG","jobId":"...","level":"info","message":"...","timestamp":"2026-06-26T12:00:00.000Z"}
{"type":"MEMORY","jobId":"...","budgetGB":12.9,"projectChromeGB":1.1,"perAccountAvgGB":0.7,"remainingCount":5,"level":"info","message":"..."}
{"type":"TICKET","jobId":"...","ticket":{ "id":"...", "type":"captcha", "title":"...", "message":"...", "resolved":false, "createdAt":"..." }}
{"type":"RESULT","jobId":"...","data":{ /* 自由格式 */ }}
{"type":"ERROR","jobId":"...","error":"...","stack":"...","recoverable":false}
{"type":"DONE","jobId":"..."}
```

> 非 JSON 的 stdout 行会被包装为 `LOG` 事件（level=info）；stderr 行被包装为 `LOG` 事件（level=error，前缀 `[stderr]`）。

后端接入只需实现 Layer 3：解析上述命令行参数、stdout 输出 NDJSON 事件流、stdin 读取控制信号、遵守优雅停止与 2 小时硬超时。

> **余额查询子命令**（独立于任务流）：`python -m chaoxing.balance` 查询火山引擎现金余额，输出单行 `BALANCE` JSON 后退出，须用装有 `volcengine-python-sdk` 的解释器拉起（默认走 `chaoxing-backend` 环境；可用 `CHAOXING_BALANCE_PYTHON` 覆盖）。详见 [API 文档 §4.7](docs/design/api.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 双管理者协作规范（分支 / PR / 提交约定 / 刷课需求流转） |
| [SECURITY.md](SECURITY.md) | 安全披露与凭据红线 |
| [docs/README.md](docs/README.md) | 文档中心索引 |
| [docs/standards/](docs/standards/) | 目录规范 / 文件规范 / 凭据规范 |
| [docs/roadmap/zhihuishu.md](docs/roadmap/zhihuishu.md) | 智慧树支持路线图（调研未开始） |
| [docs/design/api.md](docs/design/api.md) | 前后端完整 API 契约（三层协议、类型映射、安全、错误处理） |
| [docs/design/integration.md](docs/design/integration.md) | 前后端整合细节 |
| [frontend/README.md](frontend/README.md) | 前端脚本、目录结构、模式、约束 |
| [backend/README.md](backend/README.md) | 后端运行、配置、AI 答题与并发架构 |
| [docs/design/](docs/design/) | 架构设计、API 契约、整合说明、设计参考 |
| [docs/changelog/CHANGELOG.md](docs/changelog/CHANGELOG.md) | 版本变更记录 |

## 安全与稳定性要点

- **环境变量白名单**：PythonBridge 仅透传系统基础变量 + `CHAOXING_WORKSPACE` / `CHAOXING_DATA_DIR` / `CHAOXING_HEADED`，显式排除 `ARK_API_KEY` 等凭据。
- **RAM 安全检查**：任务启动前按 `(总内存 − 基线) × 75%` 与 CPU 线程数计算最大并发；运行中每 5 秒实测 Chrome 进程树收紧，超预算账号自动排队分批跑完。
- **进程治理**：单任务互斥；2 小时硬超时（SIGTERM→SIGKILL）；退出时清理孤儿 Chromium 进程。
- **渲染进程隔离**：`contextIsolation` + `sandbox` 开启，`nodeIntegration` 关闭，注入 CSP。
