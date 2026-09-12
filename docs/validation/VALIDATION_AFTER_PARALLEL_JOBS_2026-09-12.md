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
- 双平台并行的**真机（Electron + 双 Python 进程）联测**未在本轮执行（需两平台真实账号同时在线）；mock 链路与单元层已全覆盖，真机联测建议在 PR review 时由 @Arthur-Pendrag0n 或后续会话补做。

## 复现演示流（dev mock）

```text
npm run dev → 课程总览（超星）→ 左栏「全选」→「一键全自动」
→ 任务运行中切侧栏「智慧树」tab（允许）→ 课程总览（智慧树）→「全选」→「全自动（视频）」
→ 执行监控：双平台各一组 banner/阶段/席位/统计
→ 分别「全部暂停」「全部继续」「全部停止」互不影响 → 「关闭」逐组清屏
```
