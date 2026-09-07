# 修复报告 — 课程总览「仅扫描」交互逻辑

**日期**: 2026-08-07
**范围**: `frontend/src/views/CourseAtlasView.vue` + `frontend/src/app/stores/course.store.ts`
**类型**: 交互逻辑修复（UX 一致性）

> 说明：本任务原分配给并行代理 atlas_fix，该代理长时间无产出（无代码改动、无报告），
> 由 memory_hardening 接手实现，避免阻塞用户需求。

---

## 一、用户反馈

拿到新的账号列表 → 点击「一键扫描」→ 右侧出现对应账号的课程列表 → 在课程网格中选中若干课程后，
底部弹出的操作栏仍出现「仅扫描」按钮。**账号明明已经扫描过了，再提供“仅扫描”不合逻辑。**

## 二、根因

`CourseAtlasView.vue` 的底部操作栏只要 `courseStore.hasSelection` 为真就渲染 4 个按钮，
其中「仅扫描」（`startJob('course-scan')`）**无条件出现**，没有区分账号是否已经扫描过：

- 扫描完成后 `execution.store` 的 `onCompleted → reloadCoursesForJob() → courseStore.scanCourses(每个账号)`
  会把课程刷进 `coursesByAccount`；
- 但按钮的显隐只依赖“有没有选中课程”，不依赖“所选账号是否已有课程数据”。

## 三、交互决策及理由

1. **已扫描账号不再显示「仅扫描」**：新增 `courseStore.isAccountScanned(accountId)`，
   判定依据为“本会话内成功读取过发现文件（`scanCourses` 成功）”或“已存在非空课程数据”。
   底部操作栏的「仅扫描」仅在 `unscannedSelectedAccounts.length > 0` 时显示。
2. **混合状态（部分已扫描、部分未扫描）**：按钮仍然显示，但**只对未扫描的账号发起扫描**
   （`startJob('course-scan', undefined, unscannedSelectedAccounts)`），
   已扫描账号不会被重复扫描；`title` 提示将扫描的账号数。
3. **运行中防重复提交**：四个操作按钮在 `executionStore.isRunning` 时统一禁用
   （左侧「一键扫描」原本已有此逻辑）。主进程 `job.handler` 虽会拒绝并发任务，
   但 UI 层禁用更直观。
4. **空课程列表的账号**：`fetchCourses` 返回空数组时无法区分“扫描过但没课程”和“从未扫描”，
   保守地视为“可能未扫描”，保留「仅扫描」入口——对这类账号再扫一次成本极低且符合用户心智。
5. **未改动的行为**：选课自动勾选账号的联动保留（语义合理：选了某账号的课，就应把该账号纳入操作范围）；
   左侧「一键扫描」（全账号重扫）保持不变，作为主动重扫入口。

## 四、改动清单

### `frontend/src/app/stores/course.store.ts`

- 新增 `scannedAccountIds` 状态集；
- `setCoursesForAccount()`：写入非空课程时标记账号已扫描；
- `scanCourses()`：成功读取发现文件（即使为空）即标记已扫描；
- 新增 `isAccountScanned(accountId)` 并导出。

### `frontend/src/views/CourseAtlasView.vue`

- 新增 `unscannedSelectedAccounts` computed；
- `startJob()` 增加可选 `accountOverride` 参数；
- 新增 `scanUnscannedOnly()`（只扫未扫描账号）；
- 底部操作栏：「仅扫描」按需显示 + 运行中禁用全部按钮。

## 五、验证

- `npm run typecheck`（两遍 vue-tsc）：**通过**（6.6s）。
- 手工回归建议（P0/P1 见验证清单）：新账号列表 → 一键扫描 → 选中课程 → 底部不再出现「仅扫描」；
  混入未扫描账号时按钮出现且只扫未扫描账号。
