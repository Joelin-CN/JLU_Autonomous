# E2E_AUDIT_M4_CHAIN_2026-09-14 — 「仅刷题」前端按钮到 M4 solver 全链路审核（只读）

- **类型**: 端到端前置审核（用户要求的「全量全流程审核」M4/答题部分）
- **方法**: 逐层静态核对真实调用链（按钮 → store → ipcClient → Electron 主进程 → Python 入口 → solver），全部结论以源码为准
- **结论先行**: 链路一致，无阻断缺陷；两处低风险观察项见 §3

## 1. 调用链核对表（逐层）

| 层 | 文件 | 关键逻辑 | 结论 |
|----|------|---------|------|
| 按钮 | `CourseAtlasView.vue` L153 | 「仅刷题」→ `startJob('batch-exec', {focus:'quiz'})`；options 携带 `dryRun`（「模拟运行」Toggle，持久化于 settings.dryRun） | ✅ |
| Store | `execution.store.ts#startJob` | payload 原样传 `api.startJob`；成功后 `setPlan(platform, handle.memoryPlan)` + `memoryStore.start()` | ✅ |
| 映射 | `ipcClient.ts#mapMode` L44 | `'batch-exec' → 'solve_only'` | ✅ |
| Invoke | `electron/ipc/job.handler.ts` job:start | `mode = focus==='content' ? 'full' : payload.mode`（quiz 保持 solve_only）；`options.dryRun → --grade-only`；内存参数 4 项全传；ZHIHUISHU_ACCOUNTS_FILE/HEADED env 白名单注入 | ✅ |
| Python 入口 | `platforms/zhihuishu/api.py` main() | `--mode solve_only --grade-only` 已定义；`run_multi_account_generic(grade_only=cli.grade_only, dry_run=cli.dry_run)` | ✅ |
| 编排 | `core/orchestrator.py` | config 构造只传布尔（scan_only/quiz_only/grade_only/dry_run）——RunConfig 双向自洽补齐 mode（944de7c0 修复） | ✅ |
| 账号层 | `_run_account` | `quiz_only` → 跳过视频直接 `_emit_phase('solve_quiz')` → 逐课 `ZhihuishuQuizSolver(c, dry_run, grade_only)` | ✅ |
| Solver | `solvers/quiz.py` | grade_only：填答+暂存、绝不提交/交卷；已交卷卷面 `exam_page_info().submitted` → 跳过 | ✅ |
| 事件回显 | job.handler 8 事件 platform 盖章 | solve_quiz 在 PHASE_RANK 有映射（rank 3）；执行页阶段条会推进 | ✅ |

## 2. 与 CLI 验证路径的差异清单（E2E 新覆盖面）

- Electron 真实 spawn（pythonPath 来自系统设置）+ env 白名单
- UI 状态机：banner/阶段/预算仪表/日志（mock 之外的真数据）
- 工单链路：QR 登录工单在 CaptchaModal 的真实呈现
- 课程筛选：`courses: selectedCourseIds` → `--courses`（CLI 验证未带课程过滤）
- solve_quiz PHASE → 执行页 timeline 推进

## 3. 观察项（不阻断）

1. **`--courses` 过滤未实现**：job.handler 把 courseIds 传给 `--courses`，但 zhihuishu `main()` 未定义该参数 → argparse 会 SystemExit！**E2E 前必须核实**：若前端选中了课程再点「仅刷题」会带 `--courses`，智慧树入口无此旗标 → 崩溃。（超星有 `--courses`；智慧树遗漏——这是本审核发现的真缺陷，需先修）
2. `_run_account` 答题消息文案「测验 N 节」按 scanner 口径（1），solver 实际发现 6 入口——日志口径不一致，纯展示问题。

## 4. E2E 方案（审核结论：修复观察项 1 后执行）

- 轮 1（本轮）：真实账号 + 「模拟运行」开 + 仅刷题，验证全链（绪论已交卷→优雅跳过是预期结果）
- 轮 2（PR #6 合入后）：真实提交版，需可用章测（视频完成后解锁）
