# 修复日志 — vue-tsc 工具链升级 & 类型检查修复

**日期**: 2026-06-26
**范围**: `frontend/` 目录（Electron + Vue3 前端）
**背景**: 续接 2026-06-25 correctness pass。上一轮 `npx.cmd vue-tsc --noEmit` 在 Node 24.15.0 下崩溃，类型检查长期无法运行；本轮修复工具链、跑通类型检查并修掉随之暴露的真实类型错误，最后同步更新文档。

---

## 一、根因诊断

### vue-tsc 崩溃

| 项 | 值 |
|----|-----|
| Node | 24.15.0 |
| vue-tsc（修复前） | 1.8.27 |
| TypeScript | 5.9.3 |
| Vue | 3.5.38 |

`vue-tsc@1.8.x` 通过**字符串替换补丁 TS 内部实现**来注入 Vue 支持。TS 5.9 内部代码变化后，补丁找不到目标字符串，直接抛：

```
Search string not found: "/supportedTSExtensions = .*(?=;)/"
```

这是工具链兼容性问题，**不是项目代码错误**。

### tsconfig 项目引用错误

升级 vue-tsc 到 2.x 后崩溃消失，但暴露出 tsconfig 配置本身的问题：

- `tsconfig.node.json` 同时设了 `composite: true` 和 `noEmit: true` —— composite 项目必须能 emit（**TS6310**）
- `electron/**/*.ts` 同时被根配置和 node 配置 include，composite 项目 emit 的 `.d.ts` 与根项目预期冲突（**TS6305** ×7）

---

## 二、已实施修复

### Block 1：工具链

| # | 文件 | 修改 | 目的 |
|---|------|------|------|
| 1 | `frontend/package.json` | `vue-tsc` `^1.8.0` → `^2.2.0`（实装 2.2.0） | 兼容 Node 24 + TS 5.9，走正式 API 不再补丁 TS 内部 |
| 2 | `frontend/tsconfig.json` | 移除 `references`，include 收窄到 `src/**`，`types: []` | 渲染进程专用：DOM lib，不混入 Node 类型 |
| 3 | `frontend/tsconfig.node.json` | 移除 `composite`，`types: ["node"]`，include `vite.config.ts` + `electron/**` | Node 侧专用，消除 TS6305/TS6310 |
| 4 | `frontend/package.json` | `typecheck` 脚本改为两次执行：`vue-tsc -p tsconfig.json --noEmit && vue-tsc -p tsconfig.node.json --noEmit` | 渲染/Node 两套环境分开检查，避免 DOM/Node 类型冲突 |

> 设计取舍：放弃 `composite`/`references` 方案，改用两份**非重叠、非 composite** 配置 + 两遍 vue-tsc。规避了 composite 项目引用的全部坑，代价是 typecheck 跑两次（各百毫秒级，可接受）。

### Block 2：真实类型错误（跑通后暴露的 7 个）

| # | 文件:行 | 错误 | 修复 |
|---|---------|------|------|
| 5 | `src/shared/lib/ipcClient.ts:27-31` | `mapBackMode` 返回 `StartJobPayload['mode']`（后端 3 值），赋给 `JobHandle.mode`（前端 `ModeType`）类型不匹配 ×3 | 返回类型改 `ModeType`，`scan_only→course-scan`、`solve_only→batch-exec`、`full→full-auto` |
| 6 | `src/shared/lib/ipcClient.ts:150,154` | `scanCourses`/`getCourses` 直接返回 electron `Course`，缺 `totalSections`/`completedSections` | 新增 `mapElectronCourse(raw)` 适配器，从 `sections` 派生计数并映射字段 |
| 7 | `src/shared/lib/ipcClient.ts:184` | 后端 `quizSolver`（`deepseek\|doubao\|local`）赋给 `AIProvider`（`deepseek\|openai\|gemini\|qwen`），`local` 无目标 | 新增 `mapQuizSolver()`：合法值直通，其余（含 `doubao`/`local`）回退 `deepseek` |
| 8 | `src/views/AttentionQueueView.vue:23` | `PillButton variant="gold"`，但该组件只接受 `accent\|ok\|warn\|default`（无 `gold`，也无对应 CSS） | 改为 `variant="warn"` |

> 同时给 `ipcClient.ts` 的 import 补上了 `AIProvider`、`ModeType`。

### Block 3：文案修正

| # | 文件 | 修改 |
|---|------|------|
| 9 | `src/views/ExecutionStudioView.vue` | 空状态文案引用了不存在的「任务规划页面」，改为「从『课程总览』页面选择账号与课程并启动任务后…」（任务实际从 `/course-atlas` 启动） |

---

## 三、决策记录：Electron 逐账号运行时控制

确认**保留**「真子集显式抛错」行为（非本轮新增，本轮做决策与文档化）：

- Electron `*_SELECTED` handler：选中集合 == 任务全部账号 → 降级为全局控制；真子集 → `selectedControlUnsupported()` 抛错
- 理由：当前 PythonBridge 只有整进程级 `PAUSE`/`RESUME`/`STOP`，无逐账号信令。**宁可诚实失败，不伪造逐账号成功**
- Mock 模式因纯前端模拟，可真实支持逐 lane 控制
- 等 Python 后端支持真正的逐账号控制后再放开

---

## 四、文档更新

| 文件 | 变更 |
|------|------|
| `docs/api/FRONTEND_BACKEND_API.md` | v1.1 → **v1.2**：逐账号控制契约、quizSolver 映射、`JobStatus` 补 `lanes`/`phaseIndex`、事件 payload 补字段、已修复 vs 仍存在 bug 拆分、工具链说明 |
| `frontend/docs/API_SPEC.md` | **重写**：原事件 payload 全错（`accountIndex/current/total`、`phaseName/status`、`level:"OK"`、`severity/description`，均与真实 `Python*Event` 不符），按代码对齐并指向权威文档 |
| `frontend/README.md` | **重写**：脚本、目录、路由、MODES 映射、vue-tsc/逐账号控制约束 |
| `README.md`（根） | **重写**：三层协议、通道清单、Python 协议示例对齐代码 |
| `docs/handoffs/2026-06-25-frontend-correctness-pass-continuation.md` | 勾选完成项 + 新增 follow-up 完成清单与验证 |

> `docs/reference/API_REFERENCE.md` **未改** —— 它记录的是 Python 后端自身的内部 API（CLI/orchestrator/utils.py/AI），后端代码不在本仓库。

---

## 五、修改文件清单

```
frontend/package.json                             — vue-tsc 2.x + typecheck 两遍
frontend/tsconfig.json                            — 渲染进程配置（DOM，src/**）
frontend/tsconfig.node.json                       — Node 侧配置（node types，electron/**）
frontend/src/shared/lib/ipcClient.ts              — mapBackMode/mapElectronCourse/mapQuizSolver + import
frontend/src/views/AttentionQueueView.vue         — PillButton variant gold→warn
frontend/src/views/ExecutionStudioView.vue        — 空状态文案修正
```

**6 个源/配置文件。typecheck（两遍）+ build:web 均通过。**

---

## 六、验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 类型检查（渲染进程） | `vue-tsc -p tsconfig.json --noEmit` | ✅ exit 0 |
| 类型检查（Node 侧） | `vue-tsc -p tsconfig.node.json --noEmit` | ✅ exit 0 |
| 合并类型检查 | `npm.cmd run typecheck` | ✅ exit 0 |
| Web 构建 | `npm.cmd run build:web` | ✅ exit 0（built in ~820ms） |
| Electron 启动 | `npm.cmd run dev:electron` | ✅ 窗口正常拉起，关窗后干净退出（exit 0） |

---

## 七、遗留事项（仍存在的已知问题）

非本轮范围，记录备查（详见 API 文档 §9.3）：

1. 前端设置单向同步（前端→后端），无后端→前端回传
2. 多个 `Settings` 字段（videoSpeed/sectionDelay/quizRetryCount/targetAccuracy 等）不持久化到后端
3. `DONE` 事件不含完成统计，Electron 路径 `CompletionEvent.results` 全为 0
4. `campaign.store` 的 `forecast` 忽略 `strategy`/`mode`
5. `courses:list` 拒绝 accountId `0`，而 `getCourses(undefined)` 会传 `0`
6. 工单列表无去重
7. `accounts:*`/`courses:*`/`tickets:*` 仍返回 Mock 桩数据，未接真实 Python 后端
