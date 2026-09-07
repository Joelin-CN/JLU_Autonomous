# 超星学习通自动化 (Chaoxing Auto-Course)

自动完成超星学习通平台的课程任务：章节测试刷题、视频/文档自动完成、多课程批量处理。

## 快速开始

### 方式 1：JSON-line 协议（前后端分离，推荐）

通过 `chaoxing/api.py` 启动后端，使用 JSON-line 协议与 Electron 前端通信：

```bash
# 全自动处理账号 0 的所有课程
python -m chaoxing.api --job-id "job_001" --accounts "0" --mode full

# 仅扫描课程（不答题）
python -m chaoxing.api --job-id "job_002" --accounts "0" --mode scan_only

# 仅刷题（跳过内容）
python -m chaoxing.api --job-id "job_003" --accounts "0" --mode solve_only --courses "高等数学"

# 多账号并行
python -m chaoxing.api --job-id "job_004" --accounts "0,1,2" --mode full
```

**CLI 参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--job-id` | 是 | 任务唯一标识（如 `job_1719312000000_a1b2c3`） |
| `--accounts` | 是 | 账号索引，逗号分隔（如 `0` 或 `0,1,2`），最大 50 |
| `--mode` | 是 | 执行模式：`full`（全部）/ `scan_only`（扫描）/ `solve_only`（刷题） |
| `--courses` | 否 | 课程过滤，逗号分隔（子串匹配） |
| `--grade-only` | 否 | 模拟运行：填答案并 AI 评分，但不提交 |
| `--content-only` | 否 | 跳过答题阶段，仅完成内容章节 |
| `--max-concurrent` / `--budget-gb` / `--system-limit-gb` / `--per-account-estimate-gb` | 否 | Electron 按内存/CPU 计划注入；CLI 直跑可省略 |

**JSON-line 输出（stdout，每行一个 JSON）：**

| 事件 | 说明 |
|------|------|
| `PROGRESS` | 进度更新：`percent` (0-100), `message` |
| `PHASE` | 阶段变更：idle → login → scan_courses → process_sections → solve_quiz → completed |
| `LOG` | 结构化日志：`level` (debug/info/warn/error), `timestamp` (ISO 8601) |
| `MEMORY` | 运行时内存预算快照：`budgetGB` / `projectChromeGB` / `remainingCount` 等 |
| `TICKET` | 需人工介入：验证码、警告、错误 |
| `RESULT` | 结果数据载荷 |
| `ERROR` | 错误事件：`error` 消息 + 可选 `stack` traceback |
| `DONE` | 终止事件：任务结束（一定最后发出） |

**stdin 控制信号（每行一个命令）：**

| 命令 | 说明 |
|------|------|
| `PAUSE` | 在下一个安全点暂停执行 |
| `RESUME` | 恢复执行 |
| `STOP` | 优雅关闭 |

> **重要设计约束**：stdout 是 JSON-line 协议通道，**严禁**使用 `print()` 输出到 stdout。所有调试日志走 stderr。

### 方式 2：PowerShell CLI（交互式，向后兼容）

双击 `chaoxing_cli.bat` 进入交互式问答菜单。执行完毕后 BAT 会询问是否返回交互菜单运行另一个命令。

---

## 前置条件

### 软件

| 软件 | 用途 | 安装方式 |
|------|------|----------|
| **Python 3.10+** | 核心脚本运行 | 推荐 conda 环境 `chaoxing-backend`（已装全部依赖）；或 [python.org](https://www.python.org/) |
| **Node.js + npm** | playwright-cli 运行环境 | [nodejs.org](https://nodejs.org/) |
| **playwright-cli** | 浏览器自动化 | `npm install -g playwright-cli` |
| **Google Chrome** | 浏览器内核 | [google.com/chrome](https://www.google.com/chrome/) |

Python 依赖：运行时只需 `pip install -r requirements.txt`（openai 必需；volcengine-python-sdk
仅余额查询需要）。跑测试或验证码生成工具额外执行
`pip install -r requirements-dev.txt`（pytest、pillow）。

### 凭证文件

需要以下文件在 `data/passwords/` 目录下（仓库根级 `data/`，git 忽略）：

**`passwords/chaoxing.txt`** — 超星账号（支持多账户）：
```text
{
    website:"https://passport2.chaoxing.com/login?..."
    account[0]:手机号
    password[0]:密码
}
{
    website:"https://passport2.chaoxing.com/login?..."
    account[1]:手机号
    password[1]:密码
}
```

**`passwords/doubao.txt`** — 豆包 API 密钥（AI 答题，provider=doubao-api）：
```text
ARK_API_KEY="ark-..."
model="ep-xxxxxxxxxxxxx"
```

**`passwords/deepseek.txt`** — DeepSeek API 密钥（provider=deepseek-api，
OpenAI 兼容 `https://api.deepseek.com`，多模态模型可识图答题）：
```text
DEEPSEEK_API_KEY="sk-..."
model="deepseek-v4-flash-vision-exp"
```

> 切换引擎：`chaoxing_config.json → ai.provider`（或前端 设置 → AI 推理 下拉框）。

> `pwd.txt` / 旧 DeepSeek Web 后端已移除，不再需要。

---

## 项目结构

```
Chaoxing_auto/backend\
├── chaoxing/                  # ★ 核心 Python 包（47 模块，前后端分离）
│   ├── api.py                 # JSON-line 协议入口（StdioProtocol + StdinController）
│   ├── orchestrator.py        # 顶层编排器（RunConfig + run_multi_account）
│   ├── constants.py           # 全局常量（路径、信号、并发限制）
│   ├── logging_setup.py       # 结构化日志 + 协议桥接 + RAM 守卫
│   ├── config.py              # 配置管理
│   ├── session.py             # 线程级浏览器会话管理
│   ├── ai/                    # AI 答题后端
│   │   ├── doubao.py          # 豆包 API（OpenAI SDK）
│   │   ├── _base.py           # AISolver 抽象基类
│   │   ├── router.py          # AI 后端路由
│   │   └── prompts.py         # 提示词构建
│   ├── browser/               # 浏览器自动化层
│   │   ├── engine.py          # playwright-cli 底层封装
│   │   ├── js_runner.py       # JS 脚本注入
│   │   └── viewport.py        # 视口管理
│   ├── platform/              # 平台适配层
│   │   ├── auth.py            # 登录 + 凭证读取
│   │   ├── scanner.py         # 课程/章节扫描
│   │   ├── captcha.py         # 验证码识别
│   │   └── navigation.py      # 页面导航
│   ├── solvers/               # 答题 + 内容完成引擎
│   │   ├── quiz/              # 章节测试刷题
│   │   └── content/           # 视频/文档自动完成
│   ├── tracking/              # 进度追踪
│   ├── discover/              # 课程发现
│   └── js/                    # 注入用 JavaScript（字体解密/播放器）
├── chaoxing_config.json       # ★ 主配置（课程列表/URL/超时/重试，项目根目录）
├── scripts/                   # 向后兼容 Shim 层
│   ├── utils.py               # → chaoxing.* 重导出
│   ├── chaoxing_orchestrator.py  # ps1 CLI 入口 shim
│   └── ...
├── chaoxing_cli.ps1           # PowerShell 交互式 CLI（向后兼容）
├── chaoxing_cli.bat           # 最小启动器
└── tests/                     # 测试套件
    └── unit/                  # 单元测试（595 pass / 595）
```

> 运行时产物（`output/` / `temp/` / `logs/` / `passwords/` / `chrome-profiles/`）统一落在仓库根级 `data/`。

### 路径架构说明

所有运行时产物统一落在仓库根级 `data/`（对齐 monorepo 规范），源码目录 `chaoxing/` 保持纯净（无运行时写入）。`CHAOXING_WORKSPACE`（backend 子树 / userData/workspace）负责代码定位与配置；`CHAOXING_DATA_DIR`（`<仓库>/data` / userData/data）负责全部运行产物：

| 产物类型 | 目录 | 生命周期 |
|---------|------|---------|
| 进度状态 (JSON) | `data/output/` | 持久化（跨运行保留） |
| 课程发现快照 (JSON) | `data/output/` | 下次 scan/full 前清除 |
| 答题统计 (JSON) | `data/output/` | 持久化（累计记录，上限 200 条） |
| 临时 JS 脚本 / 截图 | `data/temp/` | `_run_js_file()` / finally 自动清理 |
| 验证码图片与答案 | `data/temp/` | 用完即删 |
| 运行日志 / 异常日志 | `data/logs/` | 按日滚动追加（`chaoxing_YYYYMMDD.log` / `chaoxing_errors_YYYYMMDD.log`） |
| 浏览器持久化档案 | `data/chrome-profiles/` | 登录态，跨运行保留（git 忽略） |
| 凭证文件 | `data/passwords/` | 手动放置（git 忽略） |

**环境变量**：`CHAOXING_WORKSPACE`（代码/配置根，后端子树）与 `CHAOXING_DATA_DIR`（运行产物根，仓库级 `data/`）由 CLI / 前端启动时自动设置；Python 侧优先读取，回退到 `Path(__file__)` 自检测。无需手动设置。

---

## 配置说明

编辑 `chaoxing_config.json`（项目根目录）：

```json
{
  "session": "chaoxing-chrome",
  "playwright_cli": "playwright-cli.cmd",
  "ai": {
    "provider": "doubao-api",
    "comment": "doubao-api (fast HTTP, 唯一支持的 provider)"
  },
  "courses": [
    {
      "name": "概率论与数理统计",
      "priority": 1,
      "courseid": "255106367",
      "clazzid": "127207872",
      "cpi": "415409200"
    }
  ],
  "timeouts": {
    "page_load": 30,
    "snapshot": 15,
    "click_action": 10,
    "video_watch": 60,
    "quiz_answer": 120
  },
  "retry": {
    "quiz_max_retries": 10,
    "quiz_target_score": 100
  }
}
```

### 关键配置项

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `session` | 浏览器会话名 | `chaoxing-chrome` |
| `ai.provider` | AI 答题后端 | `doubao-api` |
| `timeouts.page_load` | 页面加载超时(秒) | 30 |
| `timeouts.video_watch` | 视频观看时长(秒) | 60 |
| `retry.quiz_max_retries` | 每题最大重试 | 10 |
| `retry.quiz_target_score` | 目标正确率(%) | 100 |

> 前端「系统设置」页会通过环境变量覆盖以上超时与重试项
> （`CHAOXING_TIMEOUT_*` / `CHAOXING_RETRY_*`）；CLI 直跑时仍读
> `chaoxing_config.json` 的默认值。

---

## 架构概览

### 多线程架构

```
chaoxing_cli.ps1
  └─ chaoxing_orchestrator.py (--all-accounts)
       ├─ Thread: chaoxing-account-0  →  session: chaoxing-chrome-0
       │    ├─ scan_courses()         →  发现未完成课程
       │    ├─ scan_course_sections() →  扫描章节树
       │    ├─ ChapterQuizSolver      →  AI刷题
       │    └─ ChapterContentBot      →  视频/文档自动完成
       ├─ Thread: chaoxing-account-1  →  session: chaoxing-chrome-1
       │    └─ (同上)
       └─ MemoryMonitor              →  运行时内存预算闸门
```

- 每个账户独立的浏览器会话 (`chaoxing-chrome-N`)
- 线程本地存储 (`threading.local`) 隔离会话状态
- 运行时内存监测（`MemoryMonitor`）按预算闸门排队，超预算账号等待
- `SHUTDOWN_FLAG` (threading.Event) 实现优雅关闭

### 答题流水线

```
solve_quiz(section)
  ├─ 1. 字体解密文本模式                 ← 快速，当前字体加密未完全破解
  ├─ 2. V2 元素截图 + 批量识图           ← 主力方案 (Strategy A)
  ├─ 3. 旧版逐题截图 + 单批识图          ← 回退
  ├─ 4. 整页截图                          ← 回退
  └─ 5. Snapshot 文本提取                 ← 最后手段
       ↓
  _fill_answers() → DOM容器隔离点击
       ↓
  _submit_quiz() → 原生提交 / Snapshot回退
       ↓
  检查成绩 → ≥100% 通过 / 重试 (最多5次)
```

### AI 后端

| 后端 | 类型 | 速度 | 配置 |
|------|------|------|------|
| `doubao-api` | HTTP API (OpenAI SDK) | 快 | `ai.provider: "doubao-api"` |
| `deepseek-web` | 浏览器自动化 | 慢 | 已移除，`ai/router.py` 不再支持 |

---

## 开发者参考

### API 接口文档

详细的三层接口文档见 **[../docs/design/reference/API_REFERENCE.md](../docs/design/reference/API_REFERENCE.md)**，涵盖：

| 章节 | 内容 |
|------|------|
| CLI 层 | bat 启动器 / ps1 参数表 / 交互菜单 / 键盘监视器 / 进度解析 / 批量测试 |
| Python Orchestrator | 命令行参数 / 多线程模型 / 课程发现流程 / 单账户全流程 |
| utils.py | 全部公共函数签名 / Playwright CLI 封装 / 登录逻辑 / 扫描逻辑 / AI 路由 |
| ChapterQuizSolver | 答题流水线 / V2 截图策略 / DOM 容器隔离点击 / QuizStats 统计 / Grade-Only 模式 |
| ChapterContentBot | 内容完成机器人接口 |
| AI 后端 | Doubao API (OpenAI SDK) / 阻塞检测 |
| JavaScript 注入 | 全部内联 JS 模式 / DOM 选择器 / iframe 操作 / 字体解密 |
| 配置文件 | 完整 JSON schema / 凭证格式 / 运行时产物 / Session 命名 |
| CLI↔Python 协议 | stdout 解析 / 特殊标记 / 优雅关闭 / 多账户并发 |

### 脚本逻辑确认 (2026-06-24)

核心逻辑经审查确认如下：

- **bat → ps1**: 最小启动器模式，bat 仅做 `chcp 65001` + `powershell -ExecutionPolicy Bypass -File`，所有逻辑在 ps1 中
- **ps1 → Python**: 通过 `System.Diagnostics.Process` 启动子进程，stdout/stderr 重定向，`OutputDataReceived` 事件驱动解析
- **Python → playwright-cli**: `utils.pw()` 封装，自动附加 session + headed 标志，JSON 编码绕过 shell 转义
- **JS 注入**: 统一 `_run_js_file()` 模式 — 写 temp → `pw_run_code_file` (shell=False) → 清理
- **AI 路由**: `ai.provider` 目前仅支持 `doubao-api`（`ai/router.py` 工厂校验）
- **多线程**: Python `threading.Thread` + `threading.local` 隔离 session，运行时信号量 + `MemoryMonitor` 控制并发
- **暂停/退出**: 统一走 **stdin 控制信号**（`PAUSE`/`RESUME`/`STOP`），Python 在安全点调用 `check_signals()` 检测；旧版基于本地文件标志位（`.pause_flag`/`.quit_flag`，及 `P`/`Q` 文件）的机制已移除

---

## 当前状态（历史快照，2026-06）

| 课程 | 进度 | Quiz | Content |
|------|------|------|---------|
| 概率论与数理统计 | 79% | 16/16 ✅ (均 98.75%) | 1.8, 5.5, 7.7 待完成 |
| 大学物理ABC（下） | 0% | 待扫描 | 待扫描 |
| 综合英语-2025 | 0% | 待扫描 | 待扫描 |
| 大学物理ABC（上） | 99% (102/103) | ✅ | 6.3 余1任务 |

---

## 已知问题

1. **Quiz 已截止** — 所有 quiz 显示"已截止，不能作答"，只能 grade-only 验证
2. **字体加密** — `_decrypt_font.js` 解密后仍有乱码，Tab0 文本模式不可用
3. **`chaoxing_cli.bat` 菜单循环** — 第一次带参数运行后返回菜单不再传参（已修复，见 2026-06-24 日志）

---

## 更新日志

| 日期 | 变更 |
|------|------|
| 2026-06-26 | **整合前整理**：配置文件 `chaoxing_config.json` 从 `scripts/` 移到项目根（`CONFIG_PATH` 同步更新）；删除 8 个重构前 `.bak` 备份；补全 `.gitignore`（顶层 `output/`、`.pytest_cache/`、前端 Node/Electron 产物）；新增整合交接文档 `INTEGRATION.md`；README 校正（测试数、stdin 控制信号、目录结构） |
| 2026-06-26 | **验证码答错重试**：修复错答案被每 5s 重提到超时的 bug（读后即删）；答错时同 `id`、保留原 `createdAt` 重发刷新图工单，前端倒计时不重置（见 `FRONTEND_BACKEND_API.md` §4.3） |
| 2026-06-26 | **验证码 TICKET 链路**：接通 `TICKET`/`RESOLVE_TICKET` 人工介入链路（后端 emit 内嵌 base64 验证码图 → 前端经 stdin 回传答案）；余额查询独立子命令 `python -m chaoxing.balance` |
| 2026-06-24 | **API 文档**：编写完整 API 接口文档 `docs/API_REFERENCE.md`（Python/JS/CLI 三层接口 + 通信协议），README 新增开发者参考章节，脚本逻辑确认 |
| 2026-06-24 | **全量优化**：4 Agent 并行审查发现 82 个问题，修复 11 P0 + 18 P1；路径整合（所有中间产物限定在项目根目录 `output/` `temp/`）；消除 3 处硬编码 WORKSPACE；修复 5 处临时文件泄漏；bat 改为最小启动器；PS1 参数引号修复 |
| 2026-06-23 | **Y/N 确认门**：所有破坏性命令新增显式 `[y/N]` 确认；`-AllAccounts` 双重确认；只读命令跳过确认 |
| 2026-06-23 | **Bug 修复**：`Join-Path` 三参数崩溃、事件订阅者泄漏、`temp/` 目录缺失崩溃、菜单无效输入递归栈溢出、`Process.Start()` 未检查返回值 |
| 2026-06-23 | `.bat` 改为薄启动器，交互菜单移入 `.ps1`（规避目录名 `()` 导致 cmd 解析崩溃） |
| 2026-06-22 | Part 1-4 全部完成，16/16 quiz 验证通过 |
| 2026-06-21 | 项目初始化，Part 1 开始 |

---

## 日志

运行日志按日滚动写入 `logs/chaoxing_YYYYMMDD.log`，格式：

```
[HH:MM:SS] [LEVEL] [thread-name] message
```

多线程模式下，每条日志带有 `[chaoxing-account-N]` 前缀以便区分。

Phase C 批量测试结果保存在 `tests/phase_c_results/`。
