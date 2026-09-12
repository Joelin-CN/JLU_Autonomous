# AGENTS.md 工作指南

本文档记录与 Codex / Claude 等 AI 代理协作开发本项目的工作模式、规范和最佳实践。

> 本文件是代理规范的**单一事实源**：根部 `CLAUDE.md` 仅为 Claude Code 提供的桥接指针，规范改动只写在这里。

---

## 项目概况

- **JLU Autonomous** —— 吉林大学网课多平台自动学习助手 monorepo：超星学习通 ✅ 全套；智慧树 🚧 建设中（登录/课程扫描 ✅、视频 ✅、答题 M4 与滑块自动求解进行中，见 `docs/roadmap/zhihuishu.md`）。项目范围仅此两个平台。
- `frontend/`（Electron + Vue 3）与 `backend/`（Python 3.10+，Playwright 浏览器自动化 + AI 答题）在同一仓库。
- 前端按 Electron 进程划分：`electron/`（主进程）/ `src/`（渲染进程，Vue 3 + Pinia）/ `src/shared/`（共享层）。
- 后端按平台分包（M1 多平台架构）：`backend/core/`（平台无关层）+ `backend/platforms/{chaoxing,zhihuishu}/`（平台实现，入口 `python -m platforms.<platform>.api`，JSON-line 协议与 Electron 通信）+ `backend/chaoxing/`（兼容垫片，旧入口 `python -m chaoxing.api` 语义不变）。
- 运行时数据统一放仓库根 `data/`（不入库），第三方参考放 `references/`（不入库）。
- 仓库为公开仓库，由双管理者（@Joelin-CN / @Arthur-Pendrag0n）异步维护；协作流程见 `CONTRIBUTING.md`，目录与文件规范见 `docs/standards/`。

---

## 目录结构

```text
JLU_Autonomous/
├── AGENTS.md                 # 本文件 - 协作指南
├── README.md                 # 项目主文档
├── CONTRIBUTING.md           # 双管理者协作规范（分支 / PR / 提交约定）
├── SECURITY.md               # 安全披露与凭据红线
├── LICENSE                   # MIT 许可证
├── .gitignore / .gitattributes
│
├── frontend/                 # Electron + Vue 3 桌面端
│   ├── electron/             # 主进程：main / preload / ipc / pythonBridge / backendPath
│   ├── src/                  # 渲染进程：app / components / router / stores / views / shared
│   ├── docs/                 # 前端本地速查文档
│   ├── package.json          # 依赖与脚本
│   └── electron-builder.yml  # 打包配置（extraResources 白名单）
│
├── backend/                  # Python 后端
│   ├── core/                 # 平台无关层：orchestrator / engine / browser / memory / ai / credentials
│   ├── platforms/            # 平台实现：chaoxing/（全套）+ zhihuishu/（登录/扫描/视频，M4 进行中）
│   ├── chaoxing/             # 兼容垫片：sys.modules 别名 + -m 入口转发（旧命令语义不变）
│   ├── scripts/              # CLI shim 与只读 JS 资产
│   ├── tests/                # pytest 测试（unit / integration / e2e）
│   ├── chaoxing_cli.ps1/.bat # PowerShell / CMD 交互式 CLI
│   ├── chaoxing_config.json  # 真实配置（git 忽略；提交 chaoxing_config.example.json）
│   └── requirements.txt
│
├── data/                     # 运行时数据（git 忽略，仅 README 入库）
│   ├── passwords/            # 凭证（chaoxing.txt / zhihuishu.txt / doubao.txt / volc_billing.txt）
│   ├── chrome-profiles/      # 浏览器持久化档案（超星平铺 / 智慧树 zhihuishu/account-N/ 含 storageState）
│   ├── screenshots/ output/ temp/ logs/ documents/
│
├── references/               # 第三方参考（git 忽略，仅 README 入库）
├── docs/                     # 文档中心
│   ├── README.md             # 文档索引（唯一入口）
│   ├── standards/            # 规范：directory / documents / secrets
│   ├── roadmap/              # 平台路线图（zhihuishu 骨架）
│   ├── design/               # 常青文档：api / integration / architecture / reference
│   ├── changelog/            # CHANGELOG.md + archive/
│   ├── reports/              # analysis / fixes / updates
│   ├── sessions/             # 会话总结与 Handoff（git 忽略）
│   ├── validation/           # 验证清单
│   └── logs/                 # 开发日志（git 忽略）
└── .github/                  # CI 工作流 / Issue 与 PR 模板 / CODEOWNERS
```

## 运行环境

### Python 后端
- 推荐 conda 环境：**`chaoxing-backend`**（安装路径各机器自定，需含 `openai` + `volcengine-python-sdk`）。
- 激活方式：`conda activate chaoxing-backend`；或前端「系统设置 → Python 路径」指向其 `python.exe`。
- 余额查询额外支持 `CHAOXING_BALANCE_PYTHON` 环境变量覆盖。

### 路径约定
- `CHAOXING_WORKSPACE`：代码 / 配置根（dev 为 `backend/`，打包后为 `userData/workspace`）。
- `CHAOXING_DATA_DIR`：运行产物根（dev 为仓库根 `data/`，打包后为 `userData/data`）。
- 代码中**禁止硬编码绝对盘符路径**；一律通过 `chaoxing/constants.py` 的常量（`WORKSPACE` / `DATA_ROOT` / `OUTPUT_DIR` / `TMP_DIR` / `LOG_DIR` / `CREDS_DIR` 等）或环境变量解析。
- 新克隆的仓库**不含 `data/`**（git 忽略）：首跑前按 `data/README.md` 初始化目录结构，或用 `CHAOXING_DATA_DIR` 指向既有数据目录（如旧工作区）。

---

## 工作模式

### 多 Agent 协作模式（推荐）

```
用户 → 主持人 Codex
       ↓
       ├─ 分析 Agent（问题定位 / 架构分析） → 返回报告，等待确认
       ├─ 前端 Agent（Electron / Vue / IPC） → 独立完成，返回结果
       ├─ 后端 Agent（chaoxing 包 / 测试） → 独立完成，返回结果
       └─ 文档 Agent（汇总修改，更新 CHANGELOG / README / docs） → 收尾
```

典型流程：问题分析与任务分解 → 并行 / 串行执行（依赖存在时串行）→ 文档同步（文档 Agent 最后执行）。

## 文档归档规则

- 每个目录最多保留一个 `README.md` 作为入口。
- 常青设计文档 → `docs/design/`；版本变更 → `docs/changelog/CHANGELOG.md`（原始 FIXLOG 归 `archive/`）。
- 带日期过程文档命名：

| 类型 | 命名格式 | 示例 | 位置 |
|------|---------|------|------|
| 分析报告 | `<MODULE>_ANALYSIS_YYYY-MM-DD.md` | `QUIZ_ANALYSIS_2026-08-07.md` | `docs/reports/analysis/` |
| 修复报告 | `<MODULE>_FIX_YYYY-MM-DD.md` | `PATH_FIX_2026-08-07.md` | `docs/reports/fixes/` |
| 更新记录 | `<MODULE>_UPDATE_YYYY-MM-DD.md` | `BACKEND_UPDATE_2026-08-07.md` | `docs/reports/updates/` |
| 会话总结 | `SESSION_LOG_YYYY-MM-DD.md` | `SESSION_LOG_2026-08-07.md` | `docs/sessions/` |
| 验证清单 | `VALIDATION_AFTER_*.md` | `VALIDATION_AFTER_2026-08-07.md` | `docs/validation/` |
| 开发日志 | `YYYY-MM-DD_<topic>.md` | `2026-08-07_path_audit.md` | `docs/logs/` |

## Git 工作流规范

- 双管理者异步协作：一律 feature 分支 + PR，**禁止直推 `main`**；详细流程见 `CONTRIBUTING.md`。
- 提交信息遵循 Conventional Commits：`feat` / `fix` / `docs` / `chore` / `refactor` / `test`。
- 提交前用 `git status` 确认只包含本次变更相关文件；`data/`、`references/` 内容不得入提交。
- 涉及接口或架构变更时，先同步 `docs/design/` 对应文档。
- AI 代理执行 git 写操作（add / commit / push）需在该管理者授权的分支范围内进行；合并到 `main` 只能通过 PR。

## 验证驱动开发

- 每次修改后运行验证：后端 `python -m pytest tests/unit -q -s`（Windows/Py3.13 需 `-s`），前端 `npm run typecheck`。
- **新克隆前提**（本地跑单测前，CI 已在 workflow 内自动做同样的事）：
  1. `backend/` 下复制 `chaoxing_config.example.json` → `chaoxing_config.json`；
  2. 仓库根建 `data/temp`、`data/output`、`data/logs` 目录；
  3. `data/passwords/chaoxing.txt` 放至少 1 个账号（`{...}` 分块格式，占位号段即可，见 `docs/standards/secrets.md`）；跑 `test_ai_backends` 的 DeepSeek 余额用例还需 `deepseek.txt` 占位密钥；
  4. 全局安装 `@playwright/cli`（提供 `playwright-cli` 命令；npm 同名包 `playwright-cli` 是无 bin 的废弃存根）。
- 重要修复创建带日期的报告文档，记录问题发现、根因、方案、验证方法。
- 创建验证清单 `docs/validation/VALIDATION_AFTER_*.md`，明确 P0（必须）/ P1（重要）/ P2（可选）。

## 边界与安全

- `data/passwords/`、`data/chrome-profiles/` 含敏感登录态 / 凭据：**绝不提交、绝不写入文档**。
- `references/` 下的第三方代码仅供本地参考，不修改、不提交。
- `.env`、密钥、真实 `chaoxing_config.json`（含课程 ID / 进度）等敏感文件绝不写入代码或文档；提交示例用 `chaoxing_config.example.json`。
- 打包 `electron-builder.yml` 的 `extraResources` 使用白名单；新增后端文件时确认不会把运行时 / 敏感目录打进安装包。

---

**文档版本**: 0.3（backend 目录树与入口更新为 core/ + platforms/ 多平台布局；智慧树实况同步）
**创建日期**: 2026-08-07　**最近更新**: 2026-09-07
