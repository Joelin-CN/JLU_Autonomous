# 前端鲁棒性与内存感知并发 · 设计规格

**日期**: 2026-08-13
**范围**: `Chaoxing_auto/`（前端 Electron/Vue + 后端 Python/Playwright）
**状态**: 设计已获用户逐节批准，待实现

---

## 1. 背景与目标

### 1.1 问题

- 火山方舟（豆包）API key 目前只能手工编辑 `data/passwords/doubao.txt`，前端没有输入入口。
- 学习通账号只能手工编辑 `data/passwords/chaoxing.txt`，前端「账号凭据」面板是只读展示。
- 并发上限是后端硬编码 `MAX_CONCURRENT_ACCOUNTS = 10`（`backend/chaoxing/constants.py`）；前端「最大并发数」设置只存在 Electron 的 `settings.json`，从未传给后端。
- 启动前的 RAM 预检按每账号 350MB、70% 空闲内存粗估（`frontend/electron/ipc/job.handler.ts`），与用户想要的「(总内存 − 基线) × 75% 动态规划」不一致。
- PythonBridge 注入的省内存 Chromium 参数实际从未到达 Chrome：`playwright-cli open` 不支持参数透传；实测启动命令行里没有 `--disable-gpu` / `--renderer-process-limit`，反而带 `--enable-unsafe-swiftshader`。
- `ensure_chaoxing_browser` 用 `playwright-cli open <login_url>` 传带 `&` 的 URL，会被 cmd.exe 截断（实测报 `'newversion' is not recognized ...`）。
- 后端绝对 RAM 护栏（20G 告警 / 22G 节流 / 24G 急停）与机器实际内存无关。

### 1.2 实测基线（2026-08-13，本机 31.8GB）

真实 headless Chrome（`--browser=chrome --persistent`，同一工作区方式启动）：

| 场景 | Chrome 进程数 | 实测内存 |
| --- | --- | --- |
| 全新 profile · 登录页 | 8 | ≈ 0.49 GB |
| 登录后 · 个人空间页 | 8 | ≈ 0.54 GB |
| 真实课程页（mooc2-ans iframe） | 8 | ≈ 0.55 GB |

- 单实例构成：browser ~135MB + GPU(软件渲染) ~100MB + 2–3 个 renderer + utility/crashpad。
- 通过 `.playwright/cli.config.json` 的 `browser.launchOptions.args` 注入 `--disable-gpu` 等参数后（已验证可行），GPU 进程 ~100MB → ~38MB，进程数 8 → 7。
- 本机基线占用约 14.6GB；按公式预算 ≈ 12.9GB。

### 1.3 目标

1. 前端直接配置火山 API key 与模型接入点 ID，并提供连通性测试。
2. 前端直接增删改学习通账号，或指定自定义账号文件路径。
3. 并发数按「内存预算 + 动态实测 + CPU 保险」自动规划，超限账号排队分批跑完，保护系统内存。
4. 顺带修复上述与鲁棒性相关的既有缺陷。

---

## 2. 已确认决策

| # | 决策点 | 结论 |
| --- | --- | --- |
| 1 | 单账号内存模型 | 启动前用校准值规划；运行中实测真实占用持续校准 |
| 2 | 基线取样时机 | 每次任务开始前取样；任务运行期间冻结 |
| 3 | CPU 保险 | 运行时读线程数，`cpuCap = max(2, 线程数 − 2)`；`最大并发 = min(内存上限, cpuCap)` |
| 4 | 人工绝对上限 | 不设；协议「最多 50 账号」仅作账号列表长度校验 |
| 5 | 超出上限 | 自动排队分批，全部跑完 |
| 6 | 运行中超预算 | 停开新实例；系统总占用逼近上限且项目自身是主因且不回落时急停 |
| 7 | API key 存储 | 写回 `data/passwords/doubao.txt`，主进程原子写、只回显尾号、配连通性测试 |
| 8 | 账号增删改 | 直接写当前生效的账号文件，后端原子写，运行中锁定编辑 |
| 9 | 账号文件路径 | 全局设置：文件选择器 + 恢复默认 + 解析校验 |
| 10 | 火山配置范围 | 仅 ARK API key + 模型 ID；账单 AK/SK 维持现有文件方式 |
| 11 | 账号身份标识 | 显式 `account[N]` 编号；删除不重排；新增复用最小空闲编号 |
| 12 | 整体架构 | 方案 1：Electron 预算中枢 + Python 执行闸门 |

---

## 3. 架构与数据流

### 3.1 职责划分

**Electron 主进程（预算中枢与写入口）**

- 新增 `frontend/electron/memory/planner.ts`：纯函数预算规划。
  - 启动前（JOB_START、spawn Python 之前）取样基线；基线扣除遗留项目 Chrome 占用。
  - 产出 plan：`{ totalGB, baselineGB, budgetGB, cpuCap, perAccountEstimateGB, maxConcurrent }`。
- 新增 `frontend/electron/ipc/ai.handler.ts`：`ai:status` / `ai:set` / `ai:test`。
  - `ai:status` 按 `DATA_DIR/passwords/doubao.txt` 解析派生状态（是否配置、模型 ID、key 尾号 4 位），**不下发完整 key**；文件不存在返回「未配置」而非报错。
  - `ai:set` 由 Node 原子写回 `DATA_DIR/passwords/doubao.txt`（临时文件 → `fsync` → `rename`，旧文件备份 `.bak`），写后读回校验。校验规则：key 非空时需 `ark-` 前缀、模型非空；key 留空表示「保持现有 key 不变」（此时文件需已存在），模型留空拒绝保存。
  - `ai:test` spawn 配置的解释器 `python -m chaoxing.ai_config test`（该命令自行读 `doubao.txt`，key 不进命令行）。
- 扩展 `frontend/electron/ipc/accounts.handler.ts`：`accounts:add` / `accounts:edit` / `accounts:remove`，spawn `python -m chaoxing.accounts <子命令>`，沿用现有环境变量白名单；附带 `CHAOXING_ACCOUNTS_FILE`（若配置了自定义路径）。
- `frontend/electron/ipc/job.handler.ts`：用 planner 替换现有 350MB/0.7 估算；`JOB_START` 时把 plan 转成后端 CLI 参数。
- `frontend/electron/python/pythonBridge.ts`：spawn 时新增 `CHAOXING_ACCOUNTS_FILE` 转发；停止传 `--chromium-flags`（该链路已被证明无效，予以移除）。
- `frontend/electron/ipc/status.handler.ts`：`Settings` 增加 `accountsFilePath`、`concurrencyTarget`、`perAccountEstimateGB` 字段。

**后端 Python（执行闸门与采样）**

- 新增 `backend/chaoxing/memory.py`：
  - `measure_project_chrome_gb()`：PowerShell CIM 按 `CHROME_PROFILES_DIR/account-*` 命令行过滤 chrome.exe，汇总 WorkingSetSize；
  - `gate_open()`：打开新 Chrome 前的预算闸门（当前占用 + 有效估算 ≤ 预算才放行，否则每 5s 重试，尊重 SHUTDOWN_FLAG）；
  - 监视线程：每 5s 采样，维护 EWMA 单实例均值，判定急停，emit `MEMORY` 事件。
- `backend/chaoxing/constants.py`：删除模块级 `ACCOUNT_SEMAPHORE`；保留 `MAX_ACCOUNTS = 50` 仅作列表长度校验。
- `backend/chaoxing/api.py`：
  - 新 CLI 参数 `--max-concurrent`、`--system-limit-gb`、`--per-account-estimate-gb`；
  - 按参数创建动态信号量并传给 `run_multi_account`；
  - 协议新增 `MEMORY` 事件；`PROGRESS` 事件增加可选 `accountId`；
  - 移除 `--chromium-flags` 的解析与转发（省内存参数改由配置文件承载）。
- `backend/chaoxing/orchestrator.py`：
  - `_run_account_in_thread` 排队语义：等待动态信号量（无 300s 超时），获取槽位后先 `gate_open()` 再 `ensure_logged_in`；
  - 队列状态通过带 `accountId` 的 LOG/PROGRESS 上报；
  - `run_multi_account` 接收 `max_concurrent`、`system_limit_gb`、`per_account_estimate_gb`。
- `backend/chaoxing/platform/auth.py`：
  - `ensure_chaoxing_browser` 改为 `open about:blank` + `pw_goto(login_url)`（修复 `&` 截断）；
  - `read_all_chaoxing_credentials` 支持 `CHAOXING_ACCOUNTS_FILE` 环境变量覆盖账号文件路径。
- `backend/chaoxing/accounts.py`：增加 `add` / `edit` / `remove` 子命令（显式编号、删除不重排、复用最小空位、原子写、写后重读校验、重复检测）。
- 新增 `backend/chaoxing/ai_config.py`：`test` 子命令，读 `doubao.txt` 调方舟 `GET /api/v3/models`，输出单行 JSON。

**运行时配置**

- 新增 `backend/.playwright/cli.config.json`（dev 提交入库；打包由 `ensureWorkspaceSeeded` 复制到 `userData/workspace/.playwright/cli.config.json`）：

```json
{
  "browser": {
    "launchOptions": {
      "args": [
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--renderer-process-limit=2",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync"
      ]
    }
  }
}
```

### 3.2 数据流

```
设置页(API key) → ai:set → 主进程原子写 doubao.txt → 读回校验 → toast
设置页(测试)   → ai:test → spawn chaoxing.ai_config test → JSON 结果 → toast
设置页(账号)   → accounts:add/edit/remove → spawn chaoxing.accounts → 原子写 → 重新列取
执行页         → JOB_START → planner(基线/预算/最大并发) → spawn api.py
                               (--max-concurrent --system-limit-gb --per-account-estimate-gb)
api.py        → 动态信号量排队 → 每账号 gate_open() → ensure browser → 跑课程
memory.py     → 每 5s 采样 → MEMORY 事件 → Electron 转发 → UI 预算仪表
PROGRESS.accountId → Electron lane 更新 → 队列/运行/完成状态
```

---

## 4. 内存预算算法

### 4.1 常量

| 常量 | 值 | 说明 |
| --- | --- | --- |
| `BUDGET_RATIO` | 0.75 | 预算占（总内存 − 基线）的比例 |
| `PER_ACCOUNT_INITIAL_GB` | 0.7 | 初始单实例估算（实测 0.55 + 余量） |
| `EMERGENCY_MARGIN_GB` | 1.0 | 急停余量 |
| `SAMPLE_INTERVAL_S` | 5 | 采样周期 |
| `EMERGENCY_CONSECUTIVE` | 2 | 连续超限采样次数才触发急停 |
| `PROJECT_CAUSE_RATIO` | 0.95 | 急停需项目 Chrome 占用 ≥ 0.95 × 预算 |

### 4.2 启动规划

```text
totalGB                = os.totalmem() / GiB
baselineGB             = 当前系统已用 − 遗留项目 Chrome 占用
budgetGB               = (totalGB − baselineGB) × 0.75
cpuCap                 = max(2, os.cpus().length − 2)
memMax                 = max(1, floor(budgetGB / PER_ACCOUNT_INITIAL_GB))
maxConcurrent          = min(memMax, cpuCap)
systemLimitGB          = baselineGB + budgetGB + EMERGENCY_MARGIN_GB
```

- 预算 < 1 个实例（即 `budgetGB < 0.3 + 估算`）→ 拒绝启动并展示数字。
- `perAccountEstimateGB` 允许用户在高级设置里覆盖，影响本次 plan。

### 4.3 运行语义（预算冻结，实测收紧）

- 任务内 `maxConcurrent` 冻结（决策 2）；实测只用于收紧后续开闸，不扩大并发。
- `有效估算 = max(初始估算, EWMA 实测均值)`。
- 打开 Chrome 前：`项目 Chrome 当前占用 + 有效估算 ≤ budgetGB` 才放行；否则每 5s 重试。
- 急停（决策 6 的精确化）：
  `系统总占用 ≥ systemLimitGB` 且 `项目 Chrome 占用 ≥ 0.95 × budgetGB` 连续 2 次采样 → `signal_stop()` + `SHUTDOWN_FLAG` + `MEMORY` 严重事件。
- 采样不可用（PowerShell 失败）→ 降级为仅用估算值，只告警一次，任务不中断。

### 4.4 本机代入

31.8GB 总内存、基线 14.6GB → 预算 12.9GB → `memMax = 18`；`cpuCap = 30` → `maxConcurrent = 18`。

---

## 5. 前端 UX

遵循现有 Glassmorphic 设计体系与 tokens，不另起视觉方向。新增组件：`MaskedInput`、`BudgetGauge`、`ConfirmDialog`、`FilePickerField`。签名元素 `BudgetGauge`：分段储备表（绿 <60% / 琥珀 60–85% / 红 >85%），中心大数字「剩余可开实例数」，小字注明 `min(内存, CPU)` 来源。

### 5.1 设置页

- **AI 推理 · 火山方舟**：已配置/未配置徽标、key 尾号、模型 ID；API Key 输入（已配置时留空 = 保持原值，附显示开关）；「保存并写入本地文件」「测试连通性」（成功 / 401 密钥无效 / 404 模型不存在 / 网络超时等具体原因）。
- **账号管理**：当前账号文件路径 + 「选择文件」+「恢复默认」；切换后即时解析显示 `N 个账号` 或失败原因；表格 `# / 账号(掩码) / 登录网址 / 操作`；「添加账号」弹窗（账号、密码、可选网址）校验非空与重复；编辑只改密码/网址；删除二次确认。任务运行中整面板禁用并提示。
- **运行与内存**：`BudgetGauge`（总内存/基线/预算/项目占用/单实例均值/剩余可开数）；「目标并发」滑块 `1 … 自动上限`（默认 = 自动上限）；高级折叠项「单实例估算」。
- 保留：无头模式、通知、日志保留、主题、恢复默认。

### 5.2 执行页

- 启动按钮「按队列启动 N 个账号 · 最多 M 并发」。
- 通道状态机：`等待中 → 排队中(第 N 位) → 运行中 → 完成/异常/已停止`；运行中显示该账号进度（`PROGRESS.accountId`）。
- 页顶紧凑预算小卡。

### 5.3 Dashboard

- 系统资源面板不动；新增「项目 Chrome 占用」行（`MEMORY` 事件；浏览器 mock 模式标注「模拟数据」）。

### 5.4 文案原则

- 按钮动词全程一致（保存 →「已保存」）；错误不道歉、给下一步；空账号表显示「添加第一个账号」。

---

## 6. 安全与错误处理

- 密钥/密码不进渲染层日志、不进 localStorage；后端永不下发密码；前端自行掩码账号 ID。
- 文件写操作原子化 + `.bak` 备份 + 写后读回校验；失败时保持旧文件不变并返回具体原因。
- 保持环境变量白名单、`contextIsolation + sandbox`、IPC 集中注册；`data/passwords/` 与 `chrome-profiles/` 永不提交。
- 任务运行中锁定 key/账号/账号路径的写操作；删除账号不动登录档案目录，靠显式编号防错位。
- 启动前校验：key `ark-` 前缀、模型非空、账号/密码非空、无重复、路径存在可读。
- 运行中单账号失败不拖垮任务；急停通过 STOP + `MEMORY` 事件 + 界面横幅说明。

---

## 7. 协议与 CLI 变更

### 7.1 `python -m chaoxing.api` 新参数

```text
--max-concurrent INT            动态信号量大小（Electron 计算后传入）
--system-limit-gb FLOAT        系统总占用急停阈值（基线+预算+余量）
--per-account-estimate-gb FLOAT 初始单实例估算
```

- 移除 `--chromium-flags`（省内存参数由 `.playwright/cli.config.json` 承载）。

### 7.2 协议事件

- `PROGRESS` 增加可选 `accountId`（整数）。
- 新增 `MEMORY`：

```json
{"type":"MEMORY","jobId":"...","totalGB":31.8,"baselineGB":14.6,"budgetGB":12.9,
 "projectChromeGB":1.1,"perAccountAvgGB":0.55,"remainingCount":17,
 "level":"info","message":"..."}
```

### 7.3 `python -m chaoxing.accounts`

- `list`（现有）、`add --account --password [--website]`、`edit --index --password [--website]`、`remove --index`；单行 JSON 结果；尊重 `CHAOXING_ACCOUNTS_FILE`。

### 7.4 `python -m chaoxing.ai_config test`

- 读 `doubao.txt`，调方舟 `GET /api/v3/models`，单行 JSON（成功/失败原因）。key 不进命令行。

---

## 8. 鲁棒性修复（并入）

1. 新增 `.playwright/cli.config.json` 让省内存参数真正生效（实测 GPU 进程 100MB → 38MB）。
2. `ensure_chaoxing_browser` 用 `open about:blank` + `pw_goto` 修复 URL `&` 截断。
3. 任务模式下绝对护栏 20/22/24G 替换为相对 `systemLimitGB`；CLI 直跑保留旧值兜底。
4. `maxWorkers` 设置与后端并发打通（由动态 `maxConcurrent` 取代）。

---

## 9. 测试与验证

### 9.1 后端 pytest（unit）

- `memory` 纯函数：预算公式、上限钳制、EWMA、闸门判定（注入假采样）、急停判定。
- `accounts add/edit/remove`：显式编号、删除不重排、复用空位、重复检测、原子性（tmp fixture）。
- `CHAOXING_ACCOUNTS_FILE` 覆盖；新 CLI 参数校验；动态信号量「N 线程 M 槽位最多 M 并发」（mock）；`PROGRESS.accountId` / `MEMORY` 结构。

### 9.2 前端

- `npm run typecheck`（vue-tsc 双配置）。planner 为纯函数；暂不引入新测试框架（YAGNI）。

### 9.3 验证清单

交付时创建 `docs/validation/VALIDATION_AFTER_*.md`：真实多账号排队/仪表/急停、key 连通成功与 401、增删改后重列无错位、自定义路径、headed/headless、打包后配置播种。

---

## 10. 边界与不在范围

- 账单 AK/SK 的 UI 管理（维持 `volc_billing.txt` 文件方式）。
- 多 key 池 / 密钥轮换。
- 账号稳定 ID 体系（本设计采用显式编号空位方案）。
- headed 模式的独立内存系数（沿用同一估算，后续可再测）。
- Electron 分批多 spawn 调度（本设计用后端单进程动态信号量排队）。

---

## 11. 实施顺序建议（供 writing-plans 展开）

1. 后端 `memory.py` + 动态信号量 + `api.py` 参数/事件 + `orchestrator` 排队闸门 + 测试。
2. 后端 `accounts.py` 子命令 + `ai_config.py` + `auth.py` 修复 + 配置播种。
3. Electron 主进程：planner、IPC（ai/accounts/status/job/pythonBridge）、类型与 preload。
4. 渲染层：stores、SettingsView 三面板、ExecutionStudio 队列状态、Dashboard 仪表、新组件。
5. 验证清单 + 常青文档（`docs/design/architecture.md`、`api.md`）+ CHANGELOG。

---

## 12. 已知工作区状态（实现时注意）

- 工作区有用户未提交改动：`frontend/src/shared/lib/apiClient.ts`、`frontend/src/views/DashboardView.vue`、`frontend/vite.config.ts`，以及未跟踪的 `docs/reports/analysis/REAL_FULL_VERIFICATION_2026-08-08.md`。实现时保留这些改动，仅在其基础上增量修改，不覆盖。
