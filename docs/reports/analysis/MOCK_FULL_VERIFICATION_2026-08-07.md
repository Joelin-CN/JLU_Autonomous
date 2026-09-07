# Mock 模式全链路验证报告

**日期**: 2026-08-07
**方式**: `npm run dev`（Vite web 模式，端口 5199）→ `MockApiClient`
**驱动**: playwright-cli 0.1.14（真实 Chromium），DOM 快照 + 控制台日志为证据，
截图存于 `data/temp/mock-verify/shots/`

---

## 一、功能清单与结果

| 功能域 | 验证项 | 结果 |
| --- | --- | --- |
| 启动 | Mock 模式识别（`Running in browser mode — using MockApiClient`） | ✅ |
| 控制台 | 无功能错误（唯一 1 条为 `/favicon.ico` 404） | ⚠️ P2 |
| 仪表盘 | 余额卡片 `¥326.50`、账号 8 个、系统资源轮询、今日活动时间线 | ✅ |
| 今日活动 | 任务运行后时间线随日志填充（实测 5 条） | ✅ |
| 课程总览 | 8 账号状态点/课程徽标、全选、课程网格、模拟运行开关 | ✅ |
| 课程总览 | 选中课程后操作栏仅显示 全自动/仅刷题/仅内容（**仅扫描按扫描状态隐藏**） | ✅ |
| 一键扫描 | 启动 course-scan 任务 → 跳转执行监控，3 阶段 | ✅ |
| 一键全自动 | 启动 full-auto 任务，5 阶段，8 席位（2 运行/6 待命） | ✅ |
| 执行监控 | 阶段进度、席位进度/耗时、日志控制台 | ✅ |
| 执行监控 | 全部暂停 → `已暂停` +「全部继续」；恢复 → `运行中`；全部停止 → `已停止` | ✅（修复后） |
| 验证码弹窗 | 任务 4s 后弹出，输入答案提交 / 跳过此课程均关闭弹窗 | ✅ |
| 关注队列 | 分级过滤（紧急/警告/信息）、处理完成、结果预测、执行日志 | ✅ |
| 关注队列 | 任务完成/验证码产生的工单进入队列 | ✅ |
| 系统设置 | 全部字段渲染、账号凭据表、浅/深主题切换 | ✅ |
| 系统设置 | 修改后持久化到 localStorage，刷新保留（输入框失焦提交） | ✅ |
| 系统设置 | 恢复默认设置 | ✅ |
| 仅刷题/仅内容 | 均以 batch-exec 4 阶段启动（准备批量/分配/并行/汇总） | ✅ |

## 二、本次发现并修复的 Bug

### Bug 1：Mock 模式「全部暂停」无效（功能不可用）

**现象**：暂停后横幅仍显示「运行中」，永远不出现「全部继续」；仅运行中席位变
`已暂停`，待命席位仍 `待命`。

**根因**：`MockApiClient.pauseJob()` 全局暂停时只把 `running` 席位置为 `paused`，
6 个 `pending` 席位不动；`syncHandleStatus()` 把 `pending` 视为活跃状态，
于是任务状态恒为 `running`，UI 永不进入暂停态。

**修复**：`frontend/src/shared/lib/mockClient.ts` — 全局暂停时 `running` 与
`pending` 席位一并置为 `paused`。

**验证**：启动→暂停（`已暂停`+`全部继续` 出现）→继续（回 `运行中`）→停止
（`已停止`+`关闭`）全链路通过。

### Bug 2：课程总览「模拟运行」标签文字点击无效

**现象**：点「模拟运行」文字不切换，只有点开关本体才生效。

**根因**：`<label>` 包裹 `<button role="switch">`，点击文字触发 label 激活行为
把点击转发给按钮，与 label 自身的 @click 各 toggle 一次相互抵消。

**修复**：`frontend/src/views/CourseAtlasView.vue` — label 改用
`@click.prevent="dryRun = !dryRun"` 阻止转发；开关保留 `@click.stop`。

**验证**：开关点击、文字点击均单次生效，无双重切换；`npm run typecheck` 通过。

## 三、观察项（非阻塞）

- `/favicon.ico` 404：应用未提供图标资源（P2）。
- 验证码在弹窗解决后，关注队列中的归档副本仍为 Needs Decision，需手动「处理完成」。
  这是"队列=事后归档"的设计（真实后端会再发 resolved 事件，mock 不模拟）。
- 系统设置页开关的标签文字同样不可点击（与修复前模式一致），如需要可套用 Bug 2 修法。
- 执行监控目前只暴露全局暂停/恢复/停止；store 里的逐账号控制方法（pauseSelected 等）
  未在 UI 呈现。
- mock 数据/工单/日志为内存态，刷新页面即重置（符合 mock 预期）。

## 四、改动文件

```
frontend/src/shared/lib/mockClient.ts   — Mock 暂停语义修复
frontend/src/views/CourseAtlasView.vue  — 模拟运行标签点击修复
```

## 五、验证命令

```bash
cd frontend && npm run typecheck          # ✅ 通过（两遍 vue-tsc）
# 手工复核：npm run dev → http://localhost:5199
```
