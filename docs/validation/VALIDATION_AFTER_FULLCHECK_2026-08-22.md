# 验证清单 — 全流程检查（静态 + 实机），2026-08-22

范围：基线复现 → 静态检查（测试/构建/契约/打包/敏感扫描/依赖与环境审计）→ 实机演练（真实 Electron 界面 + 3 真实账号，全程「模拟运行 grade-only」，未提交任何真实答案）→ 打包产物核验。

- 方法：Electron `--remote-debugging-port=9222` + playwright-core（CDP）驱动真实界面；关键画面截图 + 识图复核；进程级验证（playwright-cli list / tasklist）。
- 截图目录：`data/screenshots/fullcheck_2026-08-22/`（15 张）。
- 基线：FINAL_SWEEP 未提交改动经复验后提交为 `826eec8`，本次全部结论基于该 commit。

## P0（必须）— 全部通过

- [x] 后端单元测试：`pytest tests/unit -q -s` → **588 passed**（145.78s，conda `chaoxing-backend`）
- [x] 前端 `npm run typecheck` → 通过；`npm run test`（vitest）→ 2 passed；`npm run build:web` → 1.48s 构建成功
- [x] 后端全包 `compileall` 无错误；`chaoxing_config.json` JSON 结构有效
- [x] 实机全流程（模拟运行）：3 账号并发，登录（3/3 成功）→ 课程扫描（含 0/0 课程真实重扫，"单片机竞赛"真空课程被扫描后按 0/0 保留）→ process_sections（视频 `[模拟]` 标记，grade-only 生效）→ 全部暂停（横幅+3 泳道 ⏸）→ 全部继续 → 全部停止 → 统计（3 课程 / 2 章节 / 8% / 3m22s）
- [x] **Chrome 残留清理复验 ×3 次**（FINAL_SWEEP 核心修复回归）：每次停止后 `playwright-cli list` 为空、chrome.exe = 0、python.exe = 0（含一次经 API stopJob 的停止）
- [x] 打包白名单构建验证：`electron-builder --dir` 全新构建，resources/backend 仅含 `chaoxing/`、`scripts/`（恰好 3 个白名单资产）、`chaoxing_config.json`、`requirements.txt`；6 月旧构建中的 tests/、screenshots/、etc/、documents/、CLI shim 均已不再入包
- [x] 源码敏感扫描：无硬编码盘符路径、无硬编码密钥/密码（backend + frontend 源码范围）
- [x] IPC/协议契约：30 个 invoke 通道注册↔调用全对齐（无调用未注册通道）；后端 8 类 JSON-line 事件 ↔ pythonBridge known 列表一致；PAUSE/RESUME/STOP 信号与 RESOLVE_TICKET JSON 命令后端均有处理；7 个超时/重试环境变量名两端逐字匹配

## P1（重要）— 本次新发现，未修复

- [ ] **【实机复现】Python 启动失败后 UI 永远「运行中」**
  UI 路径「一键全自动」+ 无效 pythonPath：主进程 job 状态已是 `error`（消息为英文裸文 `Python process error: spawn C:/nonexistent/python.exe ENOENT`），但 16s+ 后执行监控横幅仍「🟢 运行中」、泳道卡 `Starting... 0%`，界面内无任何错误提示（仅桌面通知），需手动「全部停止」才能恢复（之后显示「已停止」而非失败）。识图复核确认无错误标记（`15-uipath-enoent-16s.png`）。疑似错误事件早于渲染层订阅到达的竞态。上一轮 P1-1（账号级失败误报完成）修复未覆盖「进程秒败」这一形态。
  证据：截图 14/15 + `getJobStatus` 返回 `status:"error"` 的对照。
- [ ] **真实 `chaoxing_config.json` 随安装包分发**
  `frontend/electron-builder.yml` extraResources 白名单显式包含 `chaoxing_config.json`（开发者真实课程列表与进度），与该文件自己的注释（敏感内容绝不能进安装包）及 AGENTS.md 规则冲突。全新构建实测在包内。应改为打包 example、首启生成或让 seeding 复制 example。
- [ ] **打包缺 `.playwright/cli.config.json`（省内存参数）**
  白名单不含 `backend/.playwright/`，而 `ensureWorkspaceSeeded()` 打包首启要从 CODE_DIR 复制该文件 → 复制静默失败（try/catch console.error），打包版 Chrome 将以无降内存 flags（--disable-gpu 等）运行，内存行为与 dev 不一致。新构建实测包内无此文件。
- [ ] **默认配置下余额查询必然失败 + 报错不可读（可移植性核心问题）**
  `settings.pythonPath` 默认空 → 5 条 spawn 路径全部落 PATH 的 `python`（本机为独立 Python 3.13，无 volcengine-python-sdk）→ 余额卡片持久「余额查询失败」。后端其实返回了可操作的中文指引（提示激活 conda 环境），但仪表盘只显示截断的 `Error invoking remote method '…'` 包装文本。相关结构性问题：5 条 spawn 路径有 3 种解释器解析逻辑（job 路径不支持任何环境变量覆盖；仅 balance 支持 `CHAOXING_BALANCE_PYTHON`）；设置保存时不校验 pythonPath 存在性/版本。
- [ ] **playwright-cli 缺失无引导性报错**（静态审计）
  新机器无 `playwright-cli.cmd` 时，`engine.py`/`auth.py` 的 `FileNotFoundError (WinError 2)` 直接以 traceback 形式冒泡为 ERROR 事件，无「请 npm i -g playwright-cli」提示；README 的"须在 PATH"仅为文档层提醒，无启动自检。

## P2（体验/一致性）— 本次新发现，未修复

- [ ] 执行席位泳道显示**完整手机号**（未打码），与课程总览/设置页的脱敏（132\*\*\*\*3918）不一致。
- [ ] 「模拟运行」开关为页面局部状态，切换视图后**静默复位为关**——防真实提交的保护可能意外失效，建议持久化或至少全局化。
- [ ] 报错语言不一致：课程/账号/余额 CLI 路径为中文友好提示（实测「找不到 Python 解释器：…请检查设置中的 Python 路径」✓），job 路径为英文裸 ENOENT（见 P1-1）。
- [ ] 课程总览「一键扫描/一键全自动」要求全选账号（`allAccountsSelected`），无法对账号子集一键运行（子集只能去执行监控页操作）。
- [ ] dev 依赖未声明：`requirements.txt` 仅 openai + volcengine-python-sdk；pytest/Pillow（tests 与 scripts 工具需要）未声明，也无 requirements-dev.txt。
- [ ] 文档失同步：`docs/design/api.md` 环境变量白名单表缺 `CHAOXING_DATA_DIR`/`CHAOXING_ACCOUNTS_FILE`/TIMEOUT_\*/RETRY_\*（与自身另一处列表矛盾）；backend/README 测试数（587/41 模块）过时（现为 588）；electron-builder.yml 注释声称 README 记载 Python 3.10+ 要求，但 frontend README 无此内容。
- [ ] `CHAOXING_TIMEOUT_SECTION_COMPLETE` 后端定义但前端从不注入（默认 15s 生效，行为无害、两端错位）。
- [ ] 无人使用的 IPC：`backend-settings:get/set`（与 settings:get/set 完全重复）、`accounts:status`（mock 桩数据）、`on-result` 事件无订阅者。
- [ ] Python 3.10+ 要求仅存在于 markdown（无 `python_requires`、无运行时版本校验，版本过旧时表现为晦涩的 import/语法错误）。
- [ ] `job:status` 不带参数报 `Job undefined not found`，报错文案不友好。
- [ ] 仪表盘「运行时长」刚启动即显示 54h，语义疑为系统 uptime 而非应用运行时长，标签易误导（待产品确认意图）。
- [ ] 前端自动化测试覆盖极薄（vitest 仅 1 文件 2 用例，相对 30 通道 IPC 面）。
- [ ] 关注队列页自动化截图超时（疑似持续动画阻止稳定性判定；仅影响自动化截屏，肉眼未见异常）。

## 新机器部署清单（依赖审计结论，回答"别人电脑没依赖怎么办"）

现状：**应用不会自动安装/检测任何依赖，缺失时只有部分场景有友好报错**（见 P1-4/P1-5）。从零跑起需要：

1. Python 3.10+（推荐 conda 环境，或在「系统设置 → Python 路径」显式指向）
2. `pip install -r backend/requirements.txt`（openai 必需；volcengine-python-sdk 仅余额查询需要）
3. 跑测试/验证码工具额外 `pip install pytest pillow`（未声明，见 P2）
4. Node.js 18+ 与 `npm i -g playwright-cli`（须在 PATH；缺失时无引导，见 P1-5）
5. 系统已安装 Google Chrome（`--browser=chrome` 持久化模式驱动；无检测）
6. `backend/chaoxing_config.json`（模板 `chaoxing_config.example.json`；打包版由首启 seeding 生成）
7. 凭证文件：`data/passwords/chaoxing.txt`（必需）、`doubao.txt`（AI 答题）、`volc_billing.txt`（余额，可选）
8. （可选）`CHAOXING_BALANCE_PYTHON` 指向装有 volcengine SDK 的解释器

依赖矩阵（本机实测）：PATH 裸 Python 3.13（有 openai、无 volcengine/playwright 库）可完整跑主链路（登录/扫描/内容/答题，核心零第三方依赖、openai 懒加载）——仅余额查询失败；证明主链路对依赖的要求其实很低，但没有任何文档或 UI 说明这一点。

## 上轮（2026-08-14）问题复验状态

| 上轮编号 | 结论 |
|---|---|
| P1-1 账号失败误报 100% | 已修复未回归；但发现同族新形态 P1（进程秒败 UI 卡运行中） |
| P1-2 内存采样空输出 | 未复测（本次运行窗口内未采样到对比画面） |
| P1-3 账号列表不刷新 | 未复测（本次未做账号增删） |
| P2-4 账号文件标签 | 实机正常（默认路径 + 「默认」徽标一致） |
| P2-5 停止后重启卡死会话 | 本次多次启停（含 solve_only 二次启动）未见复现 |
| P2-6 进度失真 | 本次停止后统计 8% 与实际处理量级相符，横幅未见提前 100% |
| Chrome 残留（FINAL_SWEEP） | **×3 次复验全部通过** |

## 附件

- 截图：`data/screenshots/fullcheck_2026-08-22/01…15`（01 仪表盘、02 课程总览、04 运行中、06 已暂停、07 已停止、10/11 伪 python 卡运行中、14/15 UI 路径复现、08 设置、12 关注队列、13 运行后仪表盘）
- 实机环境：Windows 10.0.26100、Electron 28.3.3（CDP Chrome/120）、conda `chaoxing-backend`（复测）/ PATH Python 3.13.6（默认配置实测）、playwright-cli 全局 npm、3 真实账号档案
- 本报告只记录不修改：所有问题未做代码改动，留待后续修复批次
