# 验证清单 — 全流程检查修复批次（2026-08-22）

对应问题来源：`VALIDATION_AFTER_FULLCHECK_2026-08-22.md`（同日上午检查发现 5 P1 + 13 P2）。
本批次修复全部 5 项 P1 与 9 项 P2；修复后静态 + 实机 + 打包三层验证。

## P0（必须）— 全部通过

### 静态
- [x] 后端单元测试：595 passed（588 基线 + 7 个新增 playwright-cli 可用性用例，`tests/unit/test_cli_availability.py`）
- [x] 前端 `npm run typecheck` 通过
- [x] 前端 vitest：11 passed（2 基线 + 9 新增：`mask.test.ts` 5 例、`ipcClient.test.ts` 4 例）
- [x] `vite build`（渲染层）与 `vite build --mode electron`（主进程）均成功

### 实机（CDP 驱动真实 Electron 界面，截图 `data/screenshots/fullcheck_2026-08-22/20-23`）
- [x] **P1-1 秒败不卡死**：伪解释器（可通过校验的 fakepython.bat，spawn 后 exit 1）经 store
  正规链路启动 → 6 秒内横幅「执行失败」、泳道「异常」+ 中文原因
  「Python 进程异常退出（exit 1）。请检查「系统设置 → Python 路径」与后端依赖。」；
  停止链路无需介入（`22-lane-terminal.png`）
- [x] **P1-4 余额显示**：仪表盘显示真实原因「volcengine-python-sdk is not installed…」，
  不再是截断的 `Error invoking remote method '…'`
- [x] **P1-4 设置校验**：保存伪路径被拒（「Python 路径无效：路径不存在（…）」）；
  `validatePython` 伪路径返回中文原因、conda 真路径返回 null（含版本探测 3.13 通过）
- [x] **P2 脱敏**：执行席位显示 `132****3918`（修复前为完整手机号）
- [x] **P2 dryRun 持久化**：开关状态跨应用重启保持 ON（settings.json `dryRun` 字段）
- [x] **P2 子集一键**：选中 1/3 账号时「一键全自动」可用并以该子集启动
- [x] **P2 job:status**：无参 → 「当前没有可查询的任务。」；未知 id → 「未找到任务 …（可能已重启应用）。」
- [x] **账号加载失败可见**：伪 pythonPath 下课程总览日志控制台出现
  「账号列表加载失败：账号操作无输出（exit 1）」（修复前静默空列表）
- [x] **正常链路无回归**：真实 pythonPath 下单账号「模拟运行」全流程
  登录 → scan_courses（含 0/0 课程真实重扫）→ 停止 → 横幅已停止 →
  `playwright-cli list` 空、chrome.exe = 0（`23-real-run.png`）
- [x] 「系统运行」标签替换歧义的「运行时长」

### 打包（electron-builder --dir 全新构建核验）
- [x] **P1-2**：包内为 `chaoxing_config.example.json`，真实 `chaoxing_config.json` 不在包内
- [x] **P1-3**：`resources/backend/.playwright/cli.config.json` 在包内（省内存参数随包分发）
- [x] 白名单其余项不变（chaoxing/、scripts/ 3 资产、requirements.txt）

## 修复清单（对照原报告编号）

| 原编号 | 内容 | 状态 |
|---|---|---|
| P1-1 | spawn 秒败 UI 卡运行中（jobId:'main' 过滤丢弃 + exit 路径不通知 + 泳道终态缺失） | ✅ 三层修复 |
| P1-2 | 真实配置入包 | ✅ example 入包 + seeding 回退 |
| P1-3 | .playwright/cli.config.json 不入包 | ✅ 白名单补齐 |
| P1-4 | 解析不统一 / 校验缺失 / 余额报错不可读 | ✅ 共享 resolver + 双重校验 + 前缀剥离 |
| P1-5 | playwright-cli 缺失无引导 | ✅ 前置探测 + 中文指引（含 7 单测） |
| P2 | 席位脱敏 / dryRun 持久化 / 子集一键 / 系统运行标签 / section_complete 注入 / job:status 中文 / 移除 backend-settings / requirements-dev / 文档同步 | ✅ 全部 |
| P2（未修，记录） | 前端 IPC 面测试覆盖扩充（独立工程）；关注队列页自动化截图超时（疑持续动画，肉眼无异常） | ⏸ 留待后续 |

## 连锁发现（本批次新增修复）

- `exit`（进程秒退）路径主进程只改状态不通知渲染层 → 与 P1-1 一并修复（显式推送 ON_ERROR）。
- 坏 pythonPath 下账号列表静默为空 → 错误进日志控制台。
- store 终态未标记活动泳道 → 终态统一标记（错误附原因）。

## 环境备注

- 全程「模拟运行（dryRun）」，未提交任何真实答案；AI 评分未触发（未走到答题段）。
- 伪解释器：`data/temp/fullcheck/fakepython.bat`（`-c` 时输出 `3 13` 骗过版本探测、
  其余参数立即 exit 1），用于确定性复现 spawn 秒败；测试后 pythonPath 已还原为空。

## 提交后验收（2026-08-22 晚，commit fbc9223）

提交推送（`21871f3` fix + `fbc9223` docs → origin/main）后，对已提交状态做一轮
完整实机验收（截图 `30-36`），全部通过：

| 验收项 | 结果 |
|---|---|
| 余额错误显示 | 真实中文原因（volcengine 指引），无 invoke 包装前缀 |
| 「系统运行」标签 | 生效（56h 8m，os.uptime 语义明确） |
| 设置行内校验 | 伪路径 → 「✗ 路径不存在（…）」；conda 路径 → 「✓ 解释器可用」并保存 |
| 余额正常链路 | pythonPath 指向 conda 后查询成功：doubao 可用余额 ¥99.93 |
| dryRun 持久化 | 跨重启保持 ON |
| 子集一键 | 1/3 选中即按钮可用，并以该子集启动 |
| 真实运行（conda 解释器） | 登录 → scan_courses 18% 推进、席位脱敏 132****3918、日志正常 |
| 暂停 / 继续 / 停止 | 横幅与泳道状态正确切换 |
| 进程清理 | 停止后 `playwright-cli list` 空、chrome.exe = 0、electron 退出干净 |
