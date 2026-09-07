# 稳定性与拟人化改造（2026-08-14）

## 问题与根因

| 级别 | 现象 | 根因 |
|------|------|------|
| P1 | 账号登录失败/线程崩溃后任务仍显示「执行完成 100%」 | `run_multi_account` 子线程吞掉失败，`api.py` 仍发 `completed+DONE` |
| P1 | 未开浏览器时日志反复报 `Memory sampler degraded`，仪表盘占用显示 `—` | PowerShell 探测无 chrome 进程时 stdout 为空被判失败 |
| P1 | 账号增删改后列表不刷新（需刷新页面） | `account.store.fetchAccounts()` 的 `loaded` 缓存短路 |
| P2 | 设置页“当前账号文件”标签与实际生效文件不一致；登录网址列恒显“默认” | 标签不回读后端设置；账号列表不带 website |
| P2 | 停止后立即重启可能复用到卡死会话 | `ensure_logged_in` 未先关闭已死会话 |
| P2 | 运行中横幅提前 100%；停止后统计 100% | 单课程任务“课程完成”事件即 100；`done` 强制 100 |
| P2 | 多账号并发 `playwright-cli list` 挂死，泳道卡在登录检查 | 多线程同时打守护 socket |
| P2 | 课程扫描只扫出 1 门（实测 11 门丢失） | 课程卡片懒加载，扫描只滚动一次 |

## 修改内容

### 后端
- `chaoxing/orchestrator.py`
  - 新增 `AccountRunError`；`run_for_account` 返回成败；线程结果收集；
    `run_multi_account` 有硬失败时抛错（用户停止不算失败）。
  - 关键固定等待改为 `human_delay` 抖动（登录探测、内存门控、线程错峰）。
  - `ensure_logged_in` 快照失败时先关闭旧会话再重建。
- `chaoxing/api.py`：`run_multi_account` 返回后若 `SHUTDOWN_FLAG` 置位，
  发 `stopped + ERROR + DONE`，不再误报 completed。
- `chaoxing/memory.py`：无匹配 chrome 进程时输出 `0`，采样不再降级。
- `chaoxing/platform/auth.py`
  - 新增 `_PLAYWRIGHT_LIST_LOCK`：`playwright-cli list` 串行化 + 8s 超时兜底；
  - 登录 JS 用“短停顿 + 条件等待跳转”替代固定 5s；
  - 死页面（about:blank/崩溃）自动关会话重建。
- `chaoxing/platform/scanner.py`：课程卡片“滚动-等待-数量稳定”后再抽取；
  多处固定等待加抖动。
- `chaoxing/solvers/content/navigator.py` / `handlers.py` / `bot.py`：
  点击后等待加抖动；人工验证码轮询、文档滚动、音频轮询节奏加抖动。
- `chaoxing/solvers/quiz/solver.py` / `submitter.py`：章节测验间加入 60–120s
  随机间隔（真实提交模式；dry_run/grade_only 不等待）；提交后等待加抖动。
- `_v17_section_player.js`（`backend/scripts` 与 `backend/chaoxing/js` 同步）：
  播放失败有界重试、轮询间隔抖动、20s 无进度自恢复看门狗、暂停自恢复延迟抖动。
- `chaoxing/accounts.py`：`list` 输出携带 `website`。

### 前端
- `account.store.ts`：新增 `refreshAccounts()`，增删改后强制刷新，不再命中缓存。
- `SettingsView.vue`：账号文件标签回读后端设置；登录网址列显示真实值（默认页显示“默认”）；
  运行中提示按状态切换。
- `job.handler.ts`：账号级进度用泳道平均；未到账号级 `DONE` 前封顶 99%；
  `stopped` 状态不再被 `DONE` 翻转为 completed；完成时才把泳道置 100。
- `execution.store.ts`：渲染端横幅进度同样在非 `DONE` 事件封顶 99%。
- 类型/IPC：`Account.website` 贯通（types.ts / ipcClient / accounts.handler）。

## 验证

- 后端单元测试：587 passed。
- 前端 `npm run typecheck`：通过。
- 真实界面 E2E（真实账号 + 模拟运行不提交）：28/28 通过，覆盖仪表盘、课程扫描、
  单账号全自动（暂停/继续/停止/快速重启）、账号增删改与文件切换、失败任务状态、
  仅刷题（进入 `solve_quiz` 阶段）、三账号并发、关注队列、AI 连通性、主题。
- 识图复核：vision 技能修复后对 16 张关键截图逐张核对，全部与断言一致；
  修复前 `grade-t60s.png`（执行完成 100% vs FAILED 矛盾）与修复后
  `fail-t30s.png`（执行失败）形成前后对照。
