# 更新报告 — 双平台并行任务执行（Parallel Platform Jobs）

**日期**: 2026-09-12
**分支**: `feature/parallel-platform-jobs`（基于 `feature/renderer-platform-ui`，堆叠于 PR #3）
**交付**: PR #5；commits `187a5ef` / `804f989` / `1b6961b` / `1e33262`（+本文档 commit）
**范围**: Electron 主进程编排层 + Python 平台层（仅 `platforms/zhihuishu/api.py`）+ 渲染层执行链路 + mock 层 + 文档
**类型**: 架构升级（全局单任务 → 每平台一个执行槽位）+ 存量 bug 修复

---

## 一、背景与目标

PR #3 完成前端多平台 UI 重构（platform.store 全局上下文 / 账号课程按平台分桶 / 工单三形态 / 能力矩阵），并拍板「UI 层支持双平台并行」。但 Electron 编排层仍是**全局单任务架构**：任一时刻只允许一个活跃任务，与并行目标直接冲突。

**目标**：每平台最多 1 个活跃任务；同平台内互斥保持；跨平台并行；两平台进程总内存占用不超单机预算（红线）。**硬约束**：不改 IPC 通道名与 NDJSON 8 事件协议；Python `core/orchestrator` 平台内逻辑不动；智慧树 M4 不在范围。

## 二、盘点结论（动代码前的完整清单）

三个并行探查 + 人工核实，确认单任务假设集中在以下位置：

| 层 | 位置 | 假设 | 处置 |
|----|------|------|------|
| 主进程 | `job.handler.ts:31-32` | 模块级 `activeJobId` + 单 `bridge` 实例 | → `jobSlots.ts` 槽位表 |
| 主进程 | `job.handler.ts:479-481` | 全局互斥「任务 xxx 正在运行」 | → 按平台判占用 |
| 主进程 | `pause/resume/stopWholeJob` | 任意 jobId 的控制都打向唯一 bridge | → 按 jobId 取槽位 bridge |
| 主进程 | `job:resolve-ticket` | 载荷无 jobId，答案可能发给错误进程 | → 载荷增可选 jobId 路由 |
| 主进程 | `stopActiveJob()` | 退出只停一个任务 | → `stopAllJobs()` 遍历槽位 |
| 主进程 | `jobState.ts` 单布尔 | 任一平台结束即全局解锁 / 一个平台在跑锁死两平台 | → `isJobActive(platform?)` 派生自槽位表 |
| 渲染层 | `execution.store` | 单 jobId/lanes/phases/计时器；4/8 通道按单 jobId 过滤 | → `Record<Platform, Slot>` + 事件按 jobId 路由 |
| 渲染层 | `ipcClient.currentHandle` | platform/mode 回填串台 | → 按 jobId Map + 读后端 `raw.platform` |
| 渲染层 | mockClient 单仿真 | `startJob` 直接杀旧仿真 | → `simulations` Map（同平台替换/跨平台并存） |
| 渲染层 | platform.store 守卫 | `isRunning` 拒绝切平台 | → 移除（数据分桶使切换安全） |

**盘点中发现两个存量 bug**（详见 §四）：智慧树 argparse 崩溃（P0 级，UI 启动智慧树任务必现）与 `closeBrowserSessions` 未传 platform（停智慧树任务误关超星会话）。

**盘点中的好消息**：8 类事件 payload 天然带 jobId（Python `_write_json_line` setdefault），bridge 事件闭包已按 jobId 写 jobs Map——多实例天然安全，渲染层 4/8 通道已有按 jobId 过滤的先例。真正要动的只有「单实例假设」本身。

## 三、设计决策（已拍板）

1. **内存协调 = 策略 B「动态剩余分账」**（三选一：A 静态对半 / B 动态剩余 / C B+运行时监督）：
   - 独跑拿全额预算（现状不变，不牺牲单平台体验）；
   - 后启任务份额 = `clamp(全局预算 − 其他平台已授予之和, 最低保障 1 账号, 全局预算)`，`--max-concurrent` 按份额重算；
   - 「授予额」允许受控超卖——预算 spawn 时定死、运行时不可改，但两平台 Python 进程的 `gate_open` 闸门**实测的都是全局 Chrome 占用**（profile 同根目录），实际内存天然收敛不超单机预算；
   - `--system-limit-gb` 恒为全机值，两进程共用同一 fail-closed 急停线。红线可守。
2. **智慧树内存治理缺口 = 平台层小改**（用户授权，对「只改 electron+渲染层」约束的唯一偏离）：`platforms/zhihuishu/api.py` 补 4 个内存参数 + 挂 `core.memory` 钩子。不改则智慧树并发默认 10、无闸门无监视，红线对智慧树失守。

## 四、顺带修复的存量 bug

### 4.1 智慧树 argparse 崩溃（P0）

- **发现**：盘点发现 `job.handler.ts:527-530` 对**所有平台**无条件追加 `--max-concurrent/--budget-gb/--system-limit-gb/--per-account-estimate-gb`，而 `platforms/zhihuishu/api.py` argparse 只定义了 `--job-id/--accounts/--mode` → `parse_args()` 以 "unrecognized arguments" SystemExit(2) 退出。即：**UI 启动智慧树任务从未成功过**（M2-M3 均为 CLI 实测，未走这条路径）。
- **修复**：智慧树补齐 4 个参数（与超星同构）+ 挂钩子透传。修复后智慧树获得与超星同构的预算闸门/监视器。

### 4.2 closeBrowserSessions 未传 platform

- **发现**：`stopWholeJob`/`stopActiveJob` 调 `closeBrowserSessions(accountIds)` 时未传 `job.platform`（默认 `'chaoxing'`）→ 停智慧树任务会去关超星的 `chaoxing-chrome-N` 会话，智慧树自己的会话反而遗留。
- **修复**：两处调用补传 `job.platform`。

## 五、实现明细

### Electron 主进程（commit `804f989`）

- **`ipc/jobSlots.ts`（新）**：`JobSlotRegistry`，`Map<Platform, { jobId, bridge, grantedBudgetGB }>`。acquire（同平台抛错）/release/releaseIfCurrent（身份守卫，防旧进程迟到 exit/error 事件误清新任务槽位）/getByJobId/soleActiveSlot（无 jobId 旧载荷回落）/grantedBudgetsExcluding（分账输入）。纯逻辑不 import electron，vitest 直测。
- **`ipc/job.handler.ts`**：删 `activeJobId`/`bridge` 单例；job:start 平台归一 + 槽位互斥 + `allocateBudget` 分账；spawn 失败回滚释放槽位；resolve-ticket 按 jobId 路由（缺省回落唯一活跃槽）；`stopAllJobs()` 逐槽 STOP→taskkill 升级。
- **`ipc/jobState.ts`**：布尔 → `isJobActive(platform?)`。消费方语义：`accounts:add/edit/remove` 的 `requireIdle(platform)` **按平台锁**（超星任务运行时仍可维护智慧树账号文件）；`settings:set` 锁定项与 `ai:set` 保持**全局锁**（写的都是共享配置）。
- **`memory/planner.ts`**：新增 `allocateBudget(plan, grantedToOthers)`（见 §三公式；负数授予额防下溢；份额恒 ∈ [最低保障, 全局预算]）。
- **`types.ts`**：`ResolveTicketPayload.jobId?`；8 类 Python 事件类型增可选 `platform`（主进程转发时统一注入 `{ ...event, platform }`，仿既有 ticket 先例——协议 additive）。

### Python 平台层（commit `187a5ef`，~27 行）

`platforms/zhihuishu/api.py`：顶层 import `core.memory` 的 `MemoryMonitor/gate_open/measure_project_chrome_gb/PER_ACCOUNT_INITIAL_GB`（作为模块属性被 `core.orchestrator.ModuleRunner` 惰性读取）；argparse 4 参数；`set_ram_limit_gb` + 透传 `run_multi_account_generic`。**`core/orchestrator` 一行不动。**

### 渲染层（commit `1b6961b`）

- **`execution.store.ts`**：`slots: Record<Platform, ExecutionSlot>`（jobId/status/phaseIndex/lanes/phases/progress/计时/泳道计时各自独立；lane 计时分槽持有，跨平台同号 accountId 天然不撞）；事件监听**一次注册**按 `event.jobId` 路由；全局 tick 驱动所有活跃槽的 elapsed；`handleTerminalStatus` 仅在无其他运行槽时停 memory 订阅；`reloadCoursesForJob` 用槽自己的 platform 调 `courseStore.scanCourses(id, platform)`（修课程桶错读——原实现落到 UI 当前平台桶）；控制动作全部带 platform 首参。
- **`shared/lib/ipcClient.ts`**：`handles: Map<jobId, JobHandle>`；`startJob` 不再 dispose 全部监听（多任务路由需要）；`getJobStatus` platform 优先读后端 `raw.platform`；`onLog` 回调签名补 `jobId`/`platform`；`resolveCaptcha` 载荷透传 `jobId`。
- **`captcha.store.ts`**：submit/skip 带 `ticket.jobId`（electron 侧路由依据；`Ticket` 类型增 `jobId?`，`mapElectronTicket` 从 electron Ticket 透传——它本来就有）。
- **`views/ExecutionStudioView.vue`**：`v-for visibleSlots` 每平台一组（banner 含平台徽标/耗时/进度/独立 暂停·继续·停止·关闭 + 阶段步进 + 泳道 + 终态统计）；账号名解析带平台上下文；双空闲保留原空态。
- **守卫语义**：`platform.store.switchPlatform` 去除 isRunning 拒绝；AppSidebar 平台 tab 不再 disabled、运行小圆点 `isRunningOn(p)`；CourseAtlasView 启动/扫描按钮 `isRunningOn(currentPlatform)`；DashboardView 运行指示双平台化（双跑显示「双平台并行」）；AttentionQueueView 执行概况卡跟随当前平台槽。
- **`memory.store.ts`**：`latestByPlatform`/`planByPlatform` 分桶 + `latestFor/planFor`；兼容 getter `latest`/`plan`（最近一路/全局计划）供设置页与仪表盘单仪表。
- **`shared/lib/mockClient.ts`**：`simulations: Map<jobId, JobSimulation>`（仿真携带 platform）；同平台再启动=替换（模拟互斥）、跨平台并存；progress/phaseChange/completed/log 事件带 `platform`、log 带 jobId；演示工单带 `jobId`；演示工单定时器按各自仿真捕获引用（修旧「守卫引用全局单仿真」问题）。

## 六、验证

| 门 | 结果 |
|----|------|
| 后端 `pytest tests/unit -q -s`（conda chaoxing-backend） | **618 passed**（含智慧树 api.py 改动后） |
| 前端 `npm run typecheck`（双 project） | **0 错误** |
| 前端 `npm test`（vitest） | **50 passed**（新增 19 例：jobSlots 6 / allocateBudget 5 / mockClient 双任务 4 / execution.store 双槽路由 4） |
| dev mock 双确认（browser-use + vision.js） | 双 banner 分组渲染；暂停智慧树组不影响超星组（`⏸️已暂停`/`🟢运行中` 各自正确）；运行中切平台；超星验证码 + 智慧树扫码工单分别弹出；完成回读日志 `Scanned N courses (chaoxing)` 平台正确 |

明细与 P0/P1/P2 清单见 [VALIDATION_AFTER_PARALLEL_JOBS_2026-09-12.md](../../validation/VALIDATION_AFTER_PARALLEL_JOBS_2026-09-12.md)。

## 七、遗留与后续

- **真机双进程联测**（P2）：需两平台真实账号同时在线；mock 链路与单元层已全覆盖，建议 review 时或后续会话补做。
- mock 演示验证码 accountId 为字符串（`acct_*`）致 `parseAccountId` 报错文字压按钮——存量演示模式特有（真机工单带数字 accountId），建议 mock 演示工单改用数字 accountId。
- MEMORY 事件 mock 仍不发射（沿用现状）；执行页按平台分显预算仪表、以及策略 C 的「运行时监督（红线自动 pause 大户）」可作为后续增量。
- `job:list` 类通道未加：任务都在同一渲染会话内启动，execution.store 已各自持 jobId；应用重启后 Python 进程本就被孤儿清理收掉，无跨会话发现需求。

## 八、文档同步

- [api.md](../../design/api.md) → **v1.6**（job:start 互斥/分账语义、JobStatus 补 platform/memoryPlan、getJobStatus 按 jobId 缓存、job:resolve-ticket jobId 路由小节、事件 platform 盖章总注、双平台入口与内存参数同构、内存模型并行分账段）
- [architecture.md](../../design/architecture.md) → 新增「双平台并行任务执行（2026-09-12）」章节
- [CHANGELOG.md](../../changelog/CHANGELOG.md) → 2026-09-12（续五）条目
- [frontend/docs/API_SPEC.md](../../../frontend/docs/API_SPEC.md) → job:start 载荷/校验语义同步
- 验证清单 → `docs/validation/VALIDATION_AFTER_PARALLEL_JOBS_2026-09-12.md`
