# 修复报告 — 智慧树任务 UI 启动即崩溃（argparse 未识别参数）+ 停止任务误关他平台浏览器会话

**日期**: 2026-09-12
**范围**: `frontend/electron/ipc/job.handler.ts` / `backend/platforms/zhihuishu/api.py`
**类型**: 存量 bug 修复（随双平台并行改造一并交付，PR #5）
**状态**: ✅ 已修复并验证（pytest 618 passed）

---

## 问题一：UI 启动智慧树任务直接 SystemExit(2)（P0）

### 发现方式

双平台并行改造的代码盘点阶段：比对 `job.handler.ts` 的 CLI 参数组装与两平台 argparse 定义时发现不一致，人工读两端代码核实。

### 现象与根因

- `frontend/electron/ipc/job.handler.ts`（原 :527-530）对**所有平台**无条件追加：

  ```
  --max-concurrent / --budget-gb / --system-limit-gb / --per-account-estimate-gb
  ```

- `backend/platforms/zhihuishu/api.py` 的 argparse 只定义了 `--job-id` / `--accounts` / `--mode` 三个参数。
- Python `parse_args()` 遇到未识别参数即打印 usage 并 `SystemExit(2)`——进程秒退，渲染层收到 exit 事件显示「Python 进程异常退出」。

即：**从 UI 启动智慧树任务从未成功过**。M2/M3 实测均走 CLI 直接调 `python -m platforms.zhihuishu.api --job-id ... --accounts ...`，绕开了 electron 的参数注入路径，故一直未暴露。

### 修复方案

采用「补齐智慧树参数」而非「electron 按平台裁剪参数」：

1. `platforms/zhihuishu/api.py` argparse 补 4 个内存参数（help/语义与 `platforms/chaoxing/api.py` 同构）；
2. 顶层 import `core.memory` 的 `MemoryMonitor / gate_open / measure_project_chrome_gb / PER_ACCOUNT_INITIAL_GB`——作为模块属性被 `core.orchestrator.ModuleRunner` 惰性读取，智慧树自此获得与超星同构的**预算闸门/监视器/MEMORY 事件**（此前并发默认 10、无任何内存治理，双平台并行时红线不可守）；
3. `main()` 增加 `set_ram_limit_gb(cli.system_limit_gb)` 并把 4 参数透传 `run_multi_account_generic`。

`core/orchestrator` 一行未动（钩子机制 `core.orchestrator._OPTIONAL` 现成）。

### 为什么不选「electron 裁剪参数」

裁剪能让智慧树任务跑起来，但它仍然没有内存闸门（`max_concurrent` 回落 config 默认 10）——双平台并行时智慧树进程可以无约束开浏览器，单机内存红线失守。补参数是唯一同时修「崩溃」与「治理缺口」的方案。

### 验证

- `python -m py_compile platforms/zhihuishu/api.py` 通过；
- `pytest tests/unit -q -s` **618 passed**（含 core 编排机对 zhihuishu 钩子的用例）；
- dev mock 链路（渲染层）不受影响；真机智慧树任务启动将在双平台并行真机联测（验证清单 P2）中一并覆盖。

---

## 问题二：停止智慧树任务误关超星浏览器会话

### 发现方式

同一盘点：`closeBrowserSessions(accountIds, platform = 'chaoxing')` 已有 platform 形参，但 `stopWholeJob`（原 :268）与 `stopActiveJob`（原 :651）调用时都**没传**——`job.platform` 字段可用而未用。

### 根因与后果

playwright-cli 会话名规则是 `{platform}-chrome-{N}`（超星 `chaoxing-chrome-0`、智慧树 `zhihuishu-chrome-0`）。停智慧树任务时按默认 `'chaoxing'` 去关超星的会话：

1. 智慧树自己的 Chrome 会话遗留（靠孤儿清理兜底，但「优雅关闭→保登录态」路径失效）；
2. 若超星恰好有会话在（如并行任务），会被误关。

### 修复

两处调用补传 `job.platform ?? 'chaoxing'`；并行改造后 `stopAllJobs()` 的逐槽清理同样按各槽任务的 platform 关会话。

### 验证

- 代码路径审查（会话名拼接 `:199` 与两调用点）；
- 真机双平台同时运行后分别停止的会话隔离验证归入真机联测（P2）。

---

## 参考

- 阶段总报告：[PARALLEL_JOBS_UPDATE_2026-09-12.md](../updates/PARALLEL_JOBS_UPDATE_2026-09-12.md)
- 验证清单：[VALIDATION_AFTER_PARALLEL_JOBS_2026-09-12.md](../../validation/VALIDATION_AFTER_PARALLEL_JOBS_2026-09-12.md)
- API 契约：[api.md v1.6 §4.1](../../design/api.md)
