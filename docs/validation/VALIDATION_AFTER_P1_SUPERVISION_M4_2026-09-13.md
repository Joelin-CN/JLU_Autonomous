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
| P1-6 | M4 真机验证（grade-only，授权「填答不提交」） | ✅ **全链路通过（第 11 轮，2026-09-13 晚，用户现场扫码）**：绪论单元测试 **10/10 题**——DOM 读题型/选项 → 截图加密题干 → DeepSeek 视觉作答 → 内容映射字母（判断/单选/多选全覆盖）→ 真实点击 → 下一题逐题保存草稿 → **未提交未暂存**（草稿留页面待人工接管提交）；其余 5 个章测入口因视频未完成打不开试卷，按设计跳过；整单 `success:true`（337s）。证据：`data/logs/m4v11.log` 逐题日志 + `data/temp/zhs_quiz_q1-10.png` | 运行日志 + 截图 |
| P1-6a | 真机 8–11 轮过程修复（每处均有轮次教训） | ✅ ①AI 入参结构错位（`{index,text}` vs `{index,question,options}`，题干进不了 prompt）+ DeepSeek 密钥迁移；②RunConfig 生产构造不传 mode → 答题分支永不执行；③章测点击绑在内层 `.name` 且需先清「课程提醒」弹窗；④试卷在**新标签页** stuExamWeb 打开——试卷操作改在 exam page 对象上执行；⑤题干**加密渲染**（DOM 空文本、屏幕可见）→ 截图→AI 视觉路线；⑥末题「下一题」禁用时 `text=` 命中提示文案死循环 → getByRole('button') + 屏幕题号防循环守卫；⑦选项字母 `/^A\./` 锚定被空白失配 → `.mr10` span 精确过滤 | 提交 34d43385 / 944de7c0 / e4f82e59 |
| P1-6b | 用户复核驱动的收口（2026-09-13 深夜，DOM+vision 双通道） | ✅ 用户发现草稿部分题未勾选 → 只读巡检 + vision 交叉定位三个真问题：①多选（checkbox）不点题块内「确定」翻页即弃（两道多选草稿全空）；②末题无「下一题」可点、答案不保存；③**选中校验信号错误**——新点击只改 Vue 组件态（换 img 图标），原生 input.checked 不同步（vision 实证：视觉已选中而 checked=false）。修复（115e4e05/18bd0ea6）：多选确定钮、read_selections 双信号（checked OR 图标少数派）、暂存作业定位器回退+重试、扫码后立即导出 storageState（c9dda3d8）。**终态双确认：绪论单元测试草稿 10/10 已答、完成率 100%、未提交**（DOM：rate 100% + 答题卡全选；vision：完成率 100% + 答题卡 1-10 全蓝 + 末题 DVFS 选中）。证据：`data/temp/zhs_paper_final3.png` + `zhs_q10_before/after.png` | 提交 115e4e05 / c9dda3d8 / 18bd0ea6 |
| P1-6c | M4 真实提交链路（用户授权，2026-09-13 深夜） | ✅ **绪论单元测试真实提交：满分 20/20**——草稿（含末题暂存）完整存活到提交；submit_exam（getByRole→.btn 族定位回退 + 确认）点击成功；成绩弹窗「你本次获得的成绩是 20 分」（vision 确认）；DeepSeek 视觉作答 10/10 全对。附带修复：parse_score 成绩弹窗模式优先（通用「N分」会误匹配题目标记「(2分)」）。证据：`data/temp/zhs_paper_submitted.png` | 运行输出 + vision |
| P1-6d | E2E 轮 1（真实前端按钮，2026-09-14 00:20） | ✅ **全链路通**：智慧树「仅刷题」+模拟运行 → spawn → 过滤 → solver → DeepSeek 逐题作答 → 草稿 9/10（未提交）；`solved 1/skipped 5/failed 0`；已交卷/列表页形态优雅跳过。**E2E 抓到并修复 3 缺陷**（--courses 缺失 / Course.id=undefined / progress NaN%）。新已知问题：选项读取-点击竞态（选中校验捕获，待改按内容点击）。详见 `docs/reports/analysis/E2E_AUDIT_M4_CHAIN_2026-09-14.md` §5 | 运行日志 + UI 快照 |
| P1-7 | 滑块专项结论落档 | ✅ 分析报告 + roadmap D3 同步（维持 hint 工单；后备专项触发条件成文） | `docs/reports/analysis/ZHIHUISHU_SLIDER_ANALYSIS_2026-09-13.md` |
| P1-8 | 文档同步义务 | ✅ api.md v1.7（MEMORY 小节 / on-memory-supervision / 智慧树 solve_only 语义 / --grade-only/--dry-run）；architecture.md 监督+仪表+M4 三节；roadmap v0.3；CHANGELOG 2026-09-13（续二）；本清单 | docs/ |

## P2（可选 / 观察）

| # | 项 | 状态 |
|---|----|------|
| P2-1 | 真机内存监督越线触发 | **难以安全构造**（需真实把系统内存压到红线附近）——决策逻辑由 11 例单测覆盖；服务链路（定时器/测量/通知/推送）为薄 IO 层，留待真实高负载场景自然观察。冷却 60s / 只暂停不自动恢复 / 手动继续清标记均已单测锁定 |
| P2-2 | CIM 采样在有 Chrome 运行时的实测收益 | 粗筛快路径收益确定（无 chrome 场景彻底跳过 CIM）；有 chrome 时属性投影为尽力优化，实际收益依赖机器 WMI 状态——留待日常运行观察 MEMORY 事件密度 |
| P2-3 | M4 章测 DOM 选择器 | ✅ **已真机确认**（P1-6）：`.examPaper_subject` 族选择器有效（10 题块/题干类型/选项全命中）；题干为加密渲染（DOM 空文本）——文本路线不可用，截图→AI 视觉为标准路线（非兜底）；选项顺序每卷随机的映射已由 `map_answer_to_letters` 处理 |
| P2-4 | mock 监督介入模拟 | 未做（监督是主进程对真实进程的行为）；如需 dev 演示可后续在 mockClient 加合成 supervision 事件 |
