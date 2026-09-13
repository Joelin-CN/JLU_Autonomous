# VALIDATION — P1 增量收尾 + 智慧树 M4 答题（2026-09-13）

> 分支 `feature/parallel-platform-jobs`。改造范围：CI 触发 / CIM 采样性能 / 内存监督（策略 C）/
> 执行页分平台预算仪表 + mock MEMORY / 智慧树 M4 答题 solver + 能力矩阵翻转 / 滑块专项结论。
> 硬约束回执：NDJSON 8 事件协议**未改**；Electron 协议仅 additive 新增 `on-memory-supervision`
> push 通道；`core/orchestrator` **未动**；一切改动只进 `feature/parallel-platform-jobs`（未触 main）。

## P0（必须）

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| P0-1 | 后端单测不回归 | ✅ `tests/unit` **626 passed**（621 基线 +5 采样用例；conda `chaoxing-backend`，`python -m pytest tests/unit -q -s`） | 本地运行输出 |
| P0-2 | 后端平台套件（CI 外本地补充） | ✅ `tests/platforms` **32 passed**（含新增 M4 18 例：题型识别/答案归一/揭示解析/得分解析/AI 入参/dry_run 早退/模式分发/grade_only 贯通/VALID_PHASES） | 本地运行输出 |
| P0-3 | 前端类型检查 | ✅ 0 错误（`npm run typecheck` 双 project） | 本地运行输出 |
| P0-4 | 前端单测全绿 | ✅ **63 passed**（50 基线 +11 监督决策 +2 mock MEMORY） | 本地运行输出 |
| P0-5 | CIM 采样优化语义不变 | ✅ 脚本含粗筛守卫且位于 CIM 前 + 属性投影（recorder 断言）；缓存 TTL 内去重 / 按 root 键控 / 过期重查 / 失败不缓存（autouse 清缓存隔离旧用例） | `backend/tests/unit/test_memory.py` |
| P0-6 | 内存监督决策纯函数 | ✅ 越线选最大占用 / 压线即触发 / 冷却期不重复 / 冷却后可再介入 / 单平台生效 / 全暂停不动作 / 无运行槽位不动作 | `frontend/electron/memory/supervision.test.ts` |
| P0-7 | mock 合成 MEMORY | ✅ 平台盖章 + budgetGB 来自该仿真份额计划；双平台分账 13.5 → 0.7（下限）且 systemLimitGB 不变 | `frontend/src/shared/lib/mockClient.parallel.test.ts` |
| P0-8 | M4 模式分发 | ✅ solve_only 跳视频只跑答题 / full 先视频后答题 / scan_only 两者皆不跑 / grade_only+dry_run 贯通到 solver 构造 / dry_run 零导航（monkeypatch pw_goto 即 fail） | `backend/tests/platforms/zhihuishu/test_zhihuishu_quiz.py` |

## P1（重要）

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| P1-1 | CI 触发修复 | ✅ `ci.yml` pull_request 补 `types: [opened, synchronize, reopened, edited]`；语法由 YAML 结构核对。注意：分支上改 workflow 对本 PR CI 自身不生效（GitHub 限制），合入后生效 | `.github/workflows/ci.yml` |
| P1-2 | dev mock：执行页分平台预算仪表 | ✅ 双任务启动后执行页每组 banner 下「内存预算」横条：超星组 预算 13.5 GB·剩余 17 实例·模拟数据标记；智慧树组 预算 0.7 GB（分账下限；大数字 0 为「剩余可开实例」语义——0.7 份额扣除占用后不足再开一个，非异常） | 浏览器 DOM 快照（budgetPanels=2）+ 分屏截图 + vision 审查（布局无溢出/重叠/截断） |
| P1-3 | UI 双确认流程 | ✅ `npm run dev`（mock）→ browser-use DOM 快照 + 两屏截图 → vision.js 审查（首屏超星组 / 次屏智慧树组分别过审）；期间演示工单（验证码/扫码）按设计弹出并关闭 | 会话记录（截图 artifacts） |
| P1-4 | 监督渲染层状态链路 | ✅ memory.store.supervision 订阅 `onMemorySupervision`；`reset()` 全空闲清状态；ExecutionStudioView 顶部提示条仅 engaged 渲染（mock 不模拟介入，模板路径由 typecheck + 模板编译覆盖） | 源码 + typecheck |
| P1-5 | M4 能力矩阵翻转 | ✅ zhihuishu `solveOnly: true`、无置灰 hint；「仅刷题」按钮开放；platforms.test.ts 断言同步（solveOnly===true 且 hint undefined） | `frontend/src/shared/lib/platforms.test.ts` |
| P1-6 | 真机验证（grade-only，授权「填答不提交」） | ⚠️ **止步登录**：storageState 过期（57 Cookie 恢复后校验失败）→ QR 工单 180s 无人扫码超时 → 密码兜底登录表单填写失败 → `ERROR: 1 account(s) failed: account 0 (login failed)` 干净收尾（5min 自动 STOP 未触发即结束）。**已验证**：solve_only 模式分发正确、登录降级链按设计工作、单节异常隔离（AI 密钥缺失路径）。**未触及**：章测 DOM 抽取/填答（需登录后）。**补验条件**：现场扫码 + `doubao.txt` 真实密钥（本机缺失，deepseek.txt 为占位）；复跑命令见 roadmap §7 M4 备注 | 运行日志 `call_9bdb9bea1a0f464795548501-stdout.log` |
| P1-7 | 滑块专项结论落档 | ✅ 分析报告 + roadmap D3 同步（维持 hint 工单；后备专项触发条件成文） | `docs/reports/analysis/ZHIHUISHU_SLIDER_ANALYSIS_2026-09-13.md` |
| P1-8 | 文档同步义务 | ✅ api.md v1.7（MEMORY 小节 / on-memory-supervision / 智慧树 solve_only 语义 / --grade-only/--dry-run）；architecture.md 监督+仪表+M4 三节；roadmap v0.3；CHANGELOG 2026-09-13（续二）；本清单 | docs/ |

## P2（可选 / 观察）

| # | 项 | 状态 |
|---|----|------|
| P2-1 | 真机内存监督越线触发 | **难以安全构造**（需真实把系统内存压到红线附近）——决策逻辑由 11 例单测覆盖；服务链路（定时器/测量/通知/推送）为薄 IO 层，留待真实高负载场景自然观察。冷却 60s / 只暂停不自动恢复 / 手动继续清标记均已单测锁定 |
| P2-2 | CIM 采样在有 Chrome 运行时的实测收益 | 粗筛快路径收益确定（无 chrome 场景彻底跳过 CIM）；有 chrome 时属性投影为尽力优化，实际收益依赖机器 WMI 状态——留待日常运行观察 MEMORY 事件密度 |
| P2-3 | M4 章测 DOM 选择器 | `.examPaper_subject` 族选择器来自 M0 Track A 调研（未本地实测），真机补验（P1-6 条件满足后）为最终确认；抽取不足时截图兜底策略已备 |
| P2-4 | mock 监督介入模拟 | 未做（监督是主进程对真实进程的行为）；如需 dev 演示可后续在 mockClient 加合成 supervision 事件 |
