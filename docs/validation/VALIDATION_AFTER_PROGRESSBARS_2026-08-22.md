# 验证清单 — 进度条真实性与动态性核查修复（2026-08-22）

范围：课程总览 / 执行监控 / 关注队列三个页面的全部百分比与进度条，先以
DOM 采样 + 截图（T0/T+35s/T+75s 三时点对比）核实是否随任务推进变化，
再修复不动/失真项，修复后同口径复测。截图 `data/screenshots/fullcheck_2026-08-22/40-60`，
DOM 探针 `data/temp/fullcheck/probe.js`。

## 核查结论（修复前）

| 元素 | T0 | T1 (36%) | T2 (90%) | 判定 |
|---|---|---|---|---|
| 执行监控·泳道进度条 | 0% | 36% | 90% | ✅ 真动 |
| 执行监控·横幅百分比 | — | 36% | 90% | ✅ 真动 |
| 执行监控·阶段时间线 | 第0项running | 完全相同 | 完全相同 | ❌ 死 |
| 执行监控·阶段内进度条 | 0% | 0% | 0% | ❌ 死 |
| 关注队列·结果预测卡 | — | 50/3/M2/75% | 同 | ❌ 常量表，与任务无关 |
| 课程总览·课程卡进度 | 68/79/0… | 完全相同 | 完全相同 | ⚠️ 快照语义（完成后刷新） |
| （新发现）停止后阶段时间线 | — | — | 仍显示 running | ❌ 终态不清 |

死因：后端 PHASE 事件只带 phase 名（login/scan_courses/...），从不带
phaseIndex，且与前端 MODES 阶段文案是两套词汇 → `phaseIndex` 恒 0；
渲染层 `updateProgress` 定义后零调用；`ipcClient.getJobStatus` 优先回放
startJob 时的 phases 陈旧副本，覆盖事件驱动的更新；预测卡数据源是
`DEFAULT_FORECAST` 常量表。

## 修复内容

- **阶段时间线修活（双端）**：主进程 `job.handler` 在 PHASE 事件上按
  `PHASE_RANK`（login/scan_courses→0，process_sections/solve_quiz→3，
  completed→4，归一到 0..4）更新 `job.phaseIndex`（唯一真理源）；渲染层
  `ipcClient.getJobStatus` 不再回放陈旧 phases，始终按 phaseIndex 重算，
  running 项 progress 镜像整体进度；store `applyPhaseToSteps` 在
  onPhaseChange 即时推进（✓ 打勾）。
- **阶段内进度条改流动动画**：后端无每阶段分数，恒 0% 是误导 →
  `ProgressBar` 新增 `indeterminate` 模式（纯 CSS 流动，尊重
  prefers-reduced-motion），running 阶段显示流动条；确定性模式补
  `role=progressbar` + `aria-valuenow`。
- **终态清理**：completed → 全部 ✓；error → running 项 ✕；stopped →
  running 项 ⏹（新增 `timeline-item--stopped` 样式，RuntimePhase.status
  扩展 'stopped'）。
- **关注队列「结果预测」→「执行概况」**：删除常量假数据（50 项/M2/75%），
  改为真实数据：整体进度（ProgressBar + %，运行中实时动）、运行席位 x/y、
  人工介入（真实工单数）、状态徽标 + 耗时；无任务时显示空态提示。
- **课程总览运行角标**：卡片进度是发现文件快照（设计如此），运行中账号的
  卡片加「运行中」Chip，避免静态条被误读为实时；任务完成后自动刷新
  （既有 reloadCoursesForJob）。

## 修复后复测（DOM + 识图双口径）

- [x] 阶段推进：任务跨入 `process_sections` 后，时间线由
  「扫描课程 running」变为「扫描/分析/分配 ✓ + 自动执行 running」，
  DOM 类名 `timeline-item--completed` ×3 + `--running`（`58` 截图 + 识图确认 ✓、
  流动条、泳道 10%）
- [x] 停止终态：`timeline-item--stopped`（⏹）替换 running，✓ 保留，
  不再残留「运行中」（`59` 截图）
- [x] 关注队列概况随任务动：36% → 81% / 席位 1/1 / ▶ / 耗时递增
  （对比修复前恒 50/3/M2/75%）（`52/57` 截图）
- [x] 课程总览：运行中 8 张卡片显示「运行中」角标（`54` 截图 + 识图确认），
  停止后角标消失（`60` 截图 DOM 0 chips）
- [x] 泳道/横幅进度照常（72% → 10% 新课程重置，语义正确）
- [x] typecheck / vitest 11 passed / 双端构建通过
- [x] 停止后 chrome.exe = 0、playwright-cli list 空（无回归）

## 已知语义说明

- 扫描阶段跨入处理阶段时泳道进度会重置（新课程从 0 计）——后端语义
  （按课程汇报），非 bug；横幅百分比同步反映。
- 中间瞬时步骤（分析任务/智能分配）无后端事件，会被跨过直接打 ✓。
