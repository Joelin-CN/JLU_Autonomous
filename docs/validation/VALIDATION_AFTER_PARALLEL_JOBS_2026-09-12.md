# VALIDATION — 双平台并行任务执行（2026-09-12）

> 分支 `feature/parallel-platform-jobs`（基于 `feature/renderer-platform-ui`，堆叠于 PR #3）。
> 改造范围：Electron 编排层 per-platform 槽位 + 内存动态剩余分账 + 智慧树内存参数 + 渲染层多任务展示。
> 硬约束回执：IPC 通道名与 NDJSON 8 事件协议**未改**（仅 additive 字段）；Python `core/orchestrator` **未动**（仅 `platforms/zhihuishu/api.py` 平台层接线，已获用户授权）；智慧树 M4 不在范围。

## P0（必须）

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| P0-1 | 后端单测不回归 | ✅ **618 passed**（`conda run -n chaoxing-backend python -m pytest tests/unit -q -s`，含智慧树 api.py 改动后） | 本地运行输出 |
| P0-2 | 前端类型检查 | ✅ 0 错误（`npm run typecheck` 双 project） | 本地运行输出 |
| P0-3 | 前端单测全绿 | ✅ **50 passed**（vitest；新增 4 个测试文件共 19 例：jobSlots 6 / allocateBudget 5 / mockClient 双任务 4 / execution.store 双槽路由 4） | 本地运行输出 |
| P0-4 | 同平台互斥、跨平台并行（单元） | ✅ jobSlots：同平台 acquire 抛错、跨平台并行、releaseIfCurrent 身份守卫、grantedBudgetsExcluding 分账输入 | `frontend/electron/ipc/jobSlots.test.ts` |
| P0-5 | 内存动态分账红线 | ✅ allocateBudget：独跑全额 / 剩余份额 / 最低保障（受控超卖）/ 上下界不变式；systemLimitGB 恒全机值 | `frontend/electron/memory/planner.test.ts` |
| P0-6 | 智慧树 argparse 崩溃修复 | ✅ `platforms/zhihuishu/api.py` 定义 4 个内存参数并透传 `run_multi_account_generic`；`py_compile` 通过 + 618 单测含编排机用例 | `backend/platforms/zhihuishu/api.py` |
| P0-7 | mock 双任务生命周期 | ✅ 跨平台并存（两路事件 jobId+platform 分流）/ 同平台替换 / 停一续一 / 演示工单带 jobId | `frontend/src/shared/lib/mockClient.parallel.test.ts` |

## P1（重要）

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| P1-1 | dev mock：双平台先后起任务 | ✅ 超星「一键全自动」起任务（侧栏运行小圆点 + 状态行「任务运行中」+ 日志 `[chaoxing]` 前缀）→ 运行中切智慧树 → 「全自动（视频）」起任务 | 浏览器 DOM 快照 + 截图 |
| P1-2 | 执行页双平台分组 | ✅ DOM：`bannerCards=2`，banner 文本 `[✅执行完成📘 超星学习通100%关闭]` / `[🟢运行中🌳 智慧树0s3%全部暂停全部停止]`；视口截图 vision 分析无重叠/裁切/错位 | 截图 + vision 分析 |
| P1-3 | 组内控制独立 | ✅ 暂停智慧树组 → `[⏸️已暂停📘 超星学习通76%全部继续]`（智慧树组不受影响）；继续后恢复 `[🟢运行中31s76%]`；停止语义同理由单测覆盖 | DOM 轮询输出 |
| P1-4 | 运行中平台切换守卫 | ✅ 任务运行中智慧树 tab 可点击（不再 disabled），切换后课程总览按智慧树桶取数；课程总览启动按钮按「同平台运行中」禁用 | 浏览器交互流 |
| P1-5 | 工单流 | ✅ 超星验证码（输入型）与智慧树扫码（QR+倒计时）演示工单分别弹出；提交/跳过后弹层关闭 | 浏览器交互流 |
| P1-6 | 完成后课程回读平台正确 | ✅ 日志 `Scanned N courses (chaoxing)`（任务自己的平台，非 UI 当前平台——修课程桶错读） | 日志控制台输出 |
| P1-7 | api.md / architecture.md / CHANGELOG 同步 | ✅ api.md v1.6（job:start 互斥语义 / 分账 / resolve-ticket jobId / platform 盖章 / 智慧树参数）；architecture.md「双平台并行任务执行」章节 | docs/design/ |

## P2（观察项，不阻塞）

- mock 演示验证码的 `accountId` 为字符串 id（`acct_*`），`parseAccountId` 报错文字压在弹层按钮边框上——**存量演示模式特有**（真实后端工单带数字 accountId），与本次改造无关，建议后续给 mock 演示工单用数字 accountId。
- fullPage 截图中固定侧栏与长页面产生常见伪影（视口截图无此问题）；不影响真实渲染。
- MEMORY 事件 mock 模式仍不发射（沿用现状）；执行页按平台分显预算仪表留作后续增量。

## P0 补充 — 真机双 Python 进程联测（2026-09-13，占位账号、真实账号零学习操作）

三层真机验证全部通过（明细见下「真机联测记录」）：

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| P0-8 | 双平台真实 Python 进程并行 | ✅ 两进程同时存活（OS 级），STOP 后双双干净退出 | T2/T3 进程快照 |
| P0-9 | 预算闸门（gate_open） | ✅ 预算 0.3 < 单实例 0.7 时账号线程持续 `memory budget full, waiting...`，**零浏览器打开**；T3 中智慧树停止后超星闸门**立即放行**（动态跟随全局占用） | T2 探针 / T3 日志 |
| P0-10 | 动态剩余分账（Electron 全链路） | ✅ 智慧树先启独跑 `--budget-gb 9.83 --max-concurrent 14`；超星后启（并行放行）`--budget-gb 0.70 --max-concurrent 1` = clamp(全额−9.83, 最低保障 0.7, 全额)；`--system-limit-gb` 同口径 29.52/29.53 | T3 python.exe 命令行 |
| P0-11 | MEMORY 事件双平台 | ✅ 双进程各 3 个 MEMORY 事件（budgetGB=0.3, remainingCount=0）——智慧树协议处理器补 MEMORY 分支后生效 | T2 探针 stdout |
| P0-12 | 真实模式账号链路 | ✅ accounts:list 显式 `list` 子命令后两平台占位账号正常列出（此前智慧树 command 必填导致真实模式拉不到账号列表） | T3 应用内 |

### 真机联测记录（T1/T2/T3）

- **T1 分账数值（生产函数 + 真实测量）**：31.8GB 机器 → 全局预算 ~8.8-9.8GB（随基线波动）；独跑全额 / 后启 0.7GB 最低保障 / 急停线恒全机值，断言全过（含「授予总额 ≤ 全局 + 最低保障」的有界超卖不变式）。
- **T2 双进程闸门探针（零浏览器）**：直接 spawn `platforms.{chaoxing,zhihuishu}.api`，预算 0.3GB + system-limit 200 → 22s 双进程并行存活、各 3×MEMORY、各 4 次闸门等待、STOP 后 exit 0。
- **T3 Electron 全链路（computer-use 驱动真实窗口）**：占位账号经 `ZHIHUISHU_ACCOUNTS_FILE` 重定向；超星 3 账号 / 智慧树 1 账号真实启动；执行页双 banner 并存、侧栏双平台 running；超星后启拿 0.70GB 份额且**闸门挡住其开浏览器**（智慧树占用全局额度）→ 智慧树停止后超星闸门放行开始登录；分组「全部停止」后 python.exe 清退 count=0。
- **联测发现并当场修复**：① 智慧树 argparse 丢 `--job-id/--accounts`（首轮 T2 暴露：此前补内存参数的编辑误删，pytest/mock 均不可见——已修复并新增 `test_cli_argparse_smoke.py` 2 例防回归，pytest 620 passed）；② 智慧树协议处理器缺 MEMORY 分支（monitor 事件被静默丢弃——已补）；③ accounts:list 空参数（已显式传 `list`）。
- **联测新观察项（未修，记档）**：① `core/memory.py` MemoryMonitor 线程无异常兜底——真机多 Chrome 进程时 PowerShell CIM 采样可超 20s 超时 → 监视线程死亡（gate 的采样自带 fail-open 不受影响；建议后续 monitor 循环加 try/except + 降级）；② 扫码工单倒计时显示 `NaN:NaN`（工单 timeoutSeconds 缺省路径）；③ 智慧树占位账号 index-0 与真实账号共用 profile 目录——首轮联测曾恢复旧登录态 Cookie（仅登录态验证、未做任何学习操作即停止），后续占位联测应先移开 `storage-state.json`（本轮已移开并测完还原）。

## 复现演示流（dev mock）

```text
npm run dev → 课程总览（超星）→ 左栏「全选」→「一键全自动」
→ 任务运行中切侧栏「智慧树」tab（允许）→ 课程总览（智慧树）→「全选」→「全自动（视频）」
→ 执行监控：双平台各一组 banner/阶段/席位/统计
→ 分别「全部暂停」「全部继续」「全部停止」互不影响 → 「关闭」逐组清屏
```
