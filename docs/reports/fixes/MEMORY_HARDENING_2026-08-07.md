# 修复报告 — 内存泄漏加固（Memory Hardening）

**日期**: 2026-08-07
**范围**: 前端 Electron 主进程 / IPC / PythonBridge（本轮）；后端仅审计未改动
**类型**: 内存/资源泄漏审计 + 加固

---

## 一、日志证据时间线

### 运行时日志（data/logs/）

对 `data/logs/chaoxing_2026*.log`、`chaoxing_errors_*.log` 按关键词（内存、泄漏、memory、leak、RSS、heap、GC、残留等）检索：

- **没有发现直接标注“内存泄漏”的运行时日志条目**。`chaoxing_errors_20260625/26.log` 中的内容均为单元测试注入的 `RuntimeError: test error`（测试路径指向 `unittest/mock.py`），不是真实运行故障。
- `chaoxing_20260623.log` 中大量 “No browser session found, creating and logging in...” 属于当时的正常多账号会话创建流程；同一账号在多次任务间反复重新登录的痕迹，与后续 `orchestrator.py` finally 块显式关闭浏览器的修复相对应（见下）。

### 修复记录（docs/changelog/archive/）

| 日期 | 记录 | 泄漏类型 | 状态 |
|------|------|---------|------|
| 2026-06-24 | `CHANGELOG_20250624.md` / `FIXLOG_20250624_bat_ps1_modes.md` | 临时文件泄漏 ×5、Chrome 进程累积、事件订阅者泄漏 | 已修复 |
| 2026-06-25 | `FIXLOG_20260625_security_stability.md` | IPC 监听器泄漏（7 个 on*）、Python 子进程继承完整 env、无 RAM 防护导致 N 个 Chromium 累积 → 系统卡死/蓝屏 | 已修复（listener cleanup + env 白名单 + RAM 估算限流 + quit 时 taskkill） |
| 2026-06-26 | `FIXLOG_20260626_apiclient_singleton.md` | 5 个 store 各自 new API client + HMR 叠加实例 → mock 数据集 5 份复制 + 重复监听 | 已修复（单例化） |

### 残留目录（data/temp/_residue-*）

`data/temp/_residue-output|_residue-temp|_residue-logs` 中的内容为 **2026-08-07 当天单元测试产生的日志副本**（`_residue-logs/chaoxing_20260807.log` 内容为测试用 captcha/stats 记录）。`docs/reports/fixes/PATH_FIX_2026-08-07.md:114` 已将其定性为“测试残留，可手动清理，git 不跟踪”。**不是应用运行时产生的泄漏**，本次无需代码改动。

---

## 二、现状评估（已修复的防护机制）

审计确认以下机制在当前代码中均已生效：

| 层 | 机制 | 位置 |
|----|------|------|
| 前端 | API client 单例 + `resetApiClient()` | `frontend/src/shared/lib/apiClient.ts` |
| 前端 | 7 个 `onXxx()` 返回 cleanup、`dispose()` 清空 | `frontend/src/shared/lib/ipcClient.ts` |
| 前端 | 事件监听 cleanup 数组 + terminal 状态统一停止计时器 | `frontend/src/app/stores/execution.store.ts` |
| 前端 | tickets 上限 200、日志上限 500 行 | `attention.store.ts` / `log.store.ts` |
| 主进程 | Python 子进程 2h 安全超时、`stop()` SIGTERM→SIGKILL 链 | `frontend/electron/python/pythonBridge.ts` |
| 主进程 | 启动前 RAM 估算限流（每账号 350MB、≤70% 空闲 RAM、≤50 账号） | `frontend/electron/ipc/job.handler.ts` |
| 主进程 | quit 时 `stopActiveJob()` + `taskkill /f /im chromium.exe /t` | `frontend/electron/main.ts` |
| 主进程 | 环境变量白名单（不向 Python 泄漏密钥） | `pythonBridge.ts` / 各 handler |
| 后端 | 线程 finally 关闭浏览器 + 释放信号量 | `backend/chaoxing/orchestrator.py` |
| 后端 | tracking errors 上限 50、stats records 上限 200 | `tracking/__init__.py` / `solvers/quiz/stats.py` |
| 后端 | 系统 RAM guard（warn 20G / throttle 22G / 紧急停止 24G） | `backend/chaoxing/logging_setup.py` |
| 后端 | api.py finally 注销 protocol handler + 停止 stdin 线程 | `backend/chaoxing/api.py` |

---

## 三、本次加固改动

### 1. `frontend/electron/ipc/job.handler.ts` — 任务记录 Map 上限

- **问题**：`jobs` Map 只增不减，每个任务保留完整 `JobStatus`（含 lanes 数组）。长时间运行会无界增长。
- **修复**：新增 `MAX_RETAINED_JOBS = 20`，`retainJob()` 按插入顺序淘汰最旧任务。运行中任务不受影响（容量远大于单活动任务）。

### 2. `frontend/electron/python/pythonBridge.ts` — stdout 缓冲上限

- **问题**：`buffer` 按行拆分前无限累积。若后端异常输出大量无换行内容，缓冲无界增长。
- **修复**：`MAX_STDOUT_BUFFER_BYTES = 1MB`，超限丢弃头部并只告警一次（`bufferTruncated` 防刷屏）；`start()` 时重置缓冲与告警标志。

### 3. `frontend/electron/python/pythonBridge.ts` — spawn 失败终止清理

- **问题**：解释器路径不存在（ENOENT）等 spawn 失败时，Node 只发 `error` 事件、不发 `exit`。原代码只 emit error，`process`/`safetyTimer`/kill 定时器全部残留，`bridge.isRunning()` 恒为 true → 任务状态卡在 running、后续任务被“已有任务运行中”拒绝，且 2h 安全定时器悬空。
- **修复**：`error` 处理器中清理 kill 定时器与安全定时器、置空 `process`、emit `exit(null)`，让 job.handler 的 exit 监听统一释放 `activeJobId`/`bridge`。因 job 状态已被 error 置为终态，原有友好错误信息不会被覆盖。

### 4. `frontend/electron/ipc/course.handler.ts` / `accounts.handler.ts` — 错误路径杀子进程

- **问题**：spawn 后 `error` 分支只 reject，不杀可能已部分启动的 child。
- **修复**：`error` 分支先 `child.kill('SIGKILL')` 再 reject（幂等，失败进程 kill 返回 false 无副作用）。

---

## 四、审计后判定“无需改动”的项

- **ExecutionStudio 离开页面不 reset**：`execution.store` 为单例，离开视图时保持监听与计时是**有意行为**（返回后可继续看进度）；监听器在 terminal 状态统一清理，`globalTick` 有界（单 interval）。页面内已有“重置”按钮。
- **status.handler `tickets` 数组无上限**：当前模块内无任何写入方（事件流工单直接发渲染进程），无增长风险。若未来接入主进程持久化写入，需先加上限（已记 TODO 注释在源码处）。
- **main.ts CSP `onHeadersReceived`**：随窗口 session 生命周期销毁，无累积。
- **balance.handler 错误路径**：由并行代理（balance_fix）负责，本次未触碰以避冲突。

---

## 五、验证

- `npm run typecheck`（`vue-tsc -p tsconfig.json` + `tsconfig.node.json`）：**通过**（7.9s）。
- 后端本轮**未改动**，未重复执行 pytest（与并行代理共享工作区，避免测试写目录冲突）；相关后端防护机制已在审计中逐项确认存在。
- 残留风险提示：运行 2 小时以上的长任务仍建议按 `FIXLOG_20260625` 的验证建议抽查任务管理器中的 `chromium.exe` / `python.exe` 进程数。

---

## 六、协调层复核修正（2026-08-07）

审查 `pythonBridge.ts` spawn 失败补发 `exit(null)` 与 `job.handler.ts` 的联动时发现：
原 `exit` 监听的条件未排除 `error` 状态，会把刚设置的友好 spawn 错误信息覆盖成
`Python process exited with code null.`（与本文第三节"友好错误不会被覆盖"的表述不符）。

已修正：`job.handler.ts` 的 `exit` 监听在 `job.status === 'error'` 时保留原错误信息，
仅清理 `bridge` / `activeJobId` 引用。复核后 `npm run typecheck` 再次通过。
