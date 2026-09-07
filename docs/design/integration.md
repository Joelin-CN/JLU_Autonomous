# 前后端整合交接文档 (INTEGRATION.md)

> 面向维护本 monorepo（前端 `frontend/` + 后端 `backend/`）的工程师。
> 本文说明**后端这一侧**的边界、入口、运行约定与整合注意事项。
> IPC 协议的逐字段定义见 **[api.md](api.md)**（权威来源，本文不重复）。

---

## 1. 一句话架构

前端（Electron）作为父进程，用命令行参数拉起后端 Python 子进程，
通过 **stdin（控制信号）/ stdout（JSON-line 事件）** 双向通信。
后端不开网络端口、不落任何前端可见的本地状态——所有交互都在这条管道里。

```
Electron 主进程  ──spawn──▶  python -m chaoxing.api --job-id ... --accounts ... --mode ...
       │                              │
       │  stdin: PAUSE/RESUME/STOP    │  stdout: PROGRESS/PHASE/LOG/TICKET/RESULT/ERROR/MEMORY/DONE
       │        RESOLVE_TICKET(JSON)  │  (每行一个 JSON 对象)
       ◀──────────────────────────────
```

---

## 2. 后端入口（前端只需关心这一个）

```bash
python -m chaoxing.api --job-id <id> --accounts <idx,...> --mode <full|scan_only|solve_only> \
                       [--courses <name,...>] [--grade-only] [--content-only] \
                       [--max-concurrent <n>] [--budget-gb <gb>] \
                       [--system-limit-gb <gb>] [--per-account-estimate-gb <gb>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--job-id` | 是 | 任务唯一标识，原样回显在每个事件的 `jobId` 字段 |
| `--accounts` | 是 | 账号索引，逗号分隔（`0` 或 `0,1,2`），最大 50 |
| `--mode` | 是 | `full` / `scan_only` / `solve_only` |
| `--courses` | 否 | 课程名/ID 过滤，逗号分隔（子串匹配），省略=全部 |
| `--grade-only` | 否 | 模拟运行：填答案并 AI 评分，但不提交 |
| `--content-only` | 否 | 跳过答题阶段，仅完成内容章节 |
| `--max-concurrent` / `--budget-gb` / `--system-limit-gb` / `--per-account-estimate-gb` | 否 | Electron 按内存/CPU 计划计算后注入；CLI 直跑可省略 |

> **注意**：早期版本存在 `--chromium-flags` 参数，现已移除——省内存参数改由工作区
> `.playwright/cli.config.json` 生效，Electron 不再传该参数。

其余独立子命令：
- **余额查询**：`python -m chaoxing.balance` —— 单行 `BALANCE` JSON 或失败 `ERROR`+exit 1。须用装有 `volcengine-python-sdk` 的解释器（推荐 conda 环境 `chaoxing-backend`）拉起，凭证读 `data/passwords/volc_billing.txt`。详见 `api.md` §4.7。

---

## 3. 铁律：stdout 只走协议

**stdout 是 JSON-line 协议通道，严禁 `print()` 调试输出污染。** 所有日志/调试信息走 stderr。
后端已在 `constants.py` 强制 UTF-8 包裹 stdout/stderr（Windows）。整合时前端解析 stdout 必须**逐行 `JSON.parse`**，对非 JSON 行容错（理论上不应出现，但 stderr 偶有第三方库输出，不要混入 stdout 解析）。

事件与信号的完整枚举、字段、生命周期见 **[api.md](api.md)**：
- §4.2 stdin 入站（`PAUSE`/`RESUME`/`STOP` 明文 + `RESOLVE_TICKET` JSON）
- §4.3 stdout 出站（`PROGRESS`/`PHASE`/`LOG`/`TICKET`/`RESULT`/`ERROR`/`MEMORY`/`DONE`）

### 人工介入（验证码）是唯一的双向交互闭环
前端最容易踩坑的就是这条链路，整合时重点联调：
1. 后端 AI 识别失败 → emit `resolved:false` 的 `TICKET`（内嵌 base64 验证码图）。
2. 前端弹窗 → 用户输入 → 经 stdin 回 `RESOLVE_TICKET`（带 `answer` 或 `action:"skip"`）。
3. **答错**：后端不沉默——同 `id`、保留原 `createdAt` 重发带新图的 `resolved:false` 工单；前端用新图重开输入，倒计时不重置。用户沿用同一个 `ticketId` 重答。
4. 终态 `solved`/`skipped`/`timeout` 各 emit 一条同 `id` 的 `resolved:true` 工单关框。

> `ticket.type` 当前只产出 `captcha`；`verification`/`warning`/`error` 为**保留值，后端暂不 emit**（详见 §4.3 / §5.4）。

---

## 4. 目录职责（整合时怎么搬）

本仓库布局**就地保持**，整合时整体作为后端子树挪入 monorepo 即可。各目录职责：

| 路径 | 职责 | 整合处理 |
|------|------|----------|
| `chaoxing/` | ★ 核心 Python 包（前后端分离后的全部后端逻辑） | 整体搬移，**源码目录无运行时写入** |
| `chaoxing_config.json` | ★ 主配置（课程/URL/超时/重试），**项目根** | 跟随根目录；路径见下方注意 |
| `scripts/` | 向后兼容 shim（`utils.py` 重导出 + ps1 CLI 入口） | 可随仓库保留；前端不依赖 |
| `chaoxing_cli.ps1` / `.bat` | PowerShell 交互式 CLI（独立于前端的人工运行入口） | 保留，前端整合后仍可用于手测 |
| `tests/` | 单元测试（587 pass / 587） | 保留 |
| `data/passwords/`（仓库根级） | 凭证（**已 gitignore，绝不入库**） | 整合后仍须保证不进版本库 |
| `docs/` | 后端开发文档 / 会话 handoff | 保留或归档 |
| `docs/design/api.md` | ★ IPC 协议手册（三层权威契约） | 整合后双方统一引用 |

### 运行时产物边界（重要：整合后路径靠环境变量定位）
源码 `chaoxing/` **不写**任何运行时文件。所有产物限定在项目根下：

| 产物 | 目录 | 已 gitignore |
|------|------|:---:|
| 进度状态 / 课程发现 / 答题统计 (JSON) | `data/output/` | ✅ |
| 临时 JS、题目/验证码截图 (PNG) | `data/temp/` | ✅ |
| 运行日志 / 异常日志 | `data/logs/` | ✅ |

**环境变量 `CHAOXING_WORKSPACE`**：决定上述目录与 `chaoxing_config.json` 的根位置。
不设时回退到 `chaoxing/` 的父目录（即后端子树根 `backend/`）。
> ⚠️ **整合 monorepo 后最大的坑**：前端 spawn 后端时**必须把 `CHAOXING_WORKSPACE` 指到后端子树根 `backend/`**（即 `chaoxing_config.json` 所在层），否则配置与产物会落到错误位置；`CHAOXING_DATA_DIR` 则指向仓库级 `data/`。

---

## 5. 前置依赖（整合环境需具备）

| 依赖 | 用途 |
|------|------|
| Python 3.10+ | 后端运行 |
| `requirements.txt` 内的包 | `pip install -r requirements.txt`（含 OpenAI SDK 等；余额查询另需 `volcengine-python-sdk`，推荐 conda 环境 `chaoxing-backend`） |
| Node.js + `playwright-cli`（全局） | 浏览器自动化底座，后端通过它驱动 Chrome |
| Google Chrome | 浏览器内核 |
| `data/passwords/` 下凭证文件 | 见 README「凭证文件」节 |

> 前端 Electron 的 Node 依赖（`node_modules/`、`dist/` 等）已预先加入 `.gitignore`，整合时前端子树可直接落位不污染版本库。

---

## 6. 整合检查清单

- [ ] 前端 spawn 命令对齐 §2 参数表（`--max-concurrent` / `--budget-gb` / `--system-limit-gb` / `--per-account-estimate-gb` 由 Electron 计算后传入）
- [ ] 前端确认 `CHAOXING_WORKSPACE` 指向后端子树根、`CHAOXING_DATA_DIR` 指向仓库级 `data/`（配置与产物分层）
- [ ] stdout 逐行 `JSON.parse`，对非 JSON 行容错；不把 stderr 混入协议解析
- [ ] 验证码人工介入链路端到端联调：弹窗 → 回传 → 答错重试（新图/同 id/不重置倒计时）→ 终态关框
- [ ] `ticket.type` 仅按 `captcha` 实测；`verification`/`warning`/`error` 视为保留
- [ ] `data/passwords/`、`data/chrome-profiles/` 在版本库中确认仍被忽略
- [ ] 余额查询子命令用装有 volc SDK 的解释器拉起（与主流程解释器可不同）
- [ ] 跑一遍后端单测确认搬移无回归：`python -m pytest tests/unit/ -q -s`（Windows/Py3.13 需 `-s`）

---

## 7. 相关文档

| 文档 | 内容 |
|------|------|
| [api.md](api.md) | ★ IPC 协议权威定义（事件/信号/工单逐字段 + 前端 Store 映射） |
| [../backend/README.md](../backend/README.md) | 后端总览、快速开始、配置、架构、已知问题 |
| [reference/API_REFERENCE.md](reference/API_REFERENCE.md) | Python/JS/CLI 三层内部接口参考 |
| [architecture.md](architecture.md) | 架构概览 |
