# 文件与文档规范

> 文档怎么分类、命名、归档、同步。配套：[directory.md](directory.md)（目录职责）、[secrets.md](secrets.md)（凭据红线）。
>
> 版本 1.0 · 2026-09-07（随仓库打底建立；归档规则承接原 AGENTS.md 体系）

---

## 1. 文档分类表

| 子目录 | 类型 | 入库 | 说明 |
| --- | --- | --- | --- |
| `docs/standards/` | 规范 | ✅ | 目录 / 文件 / 凭据三份规范，低频演进 |
| `docs/roadmap/` | 路线图 | ✅ | 平台支持规划（当前：zhihuishu 骨架） |
| `docs/design/` | 常青设计文档 | ✅ | 架构 / API 契约 / 整合 / 内部接口参考，随代码演进持续更新 |
| `docs/changelog/` | 版本变更 | ✅ | `CHANGELOG.md` + `archive/` 历史归档 |
| `docs/reports/` | 过程报告 | ✅ | `analysis/` 分析、`fixes/` 修复、`updates/` 更新记录 |
| `docs/validation/` | 验证清单 | ✅ | 修复 / 阶段后的验收检查表（P0/P1/P2 分级） |
| `docs/logs/` | 开发日志 | ✅ | 日常零散记录 |
| `docs/sessions/` | 会话总结 / Handoff | ❌ | 含本地开发细节与账号信息，**仅留本地**（git 忽略） |
| `docs/handoffs/` `docs/changelogs/` `docs/superpowers/` `docs/prototypes/` | 内部工作区 | ❌ | 同上，git 忽略 |
| `frontend/docs/` `backend/README.md` | 模块本地速查 | ✅ | 紧邻模块的运行说明 |

> 判断「入库与否」的唯一标准：**内容是否可能包含真实账号、课程 ID、个人数据或仅对单机有意义的路径**。是 → 本地；否 → 入库。公开仓库里错放一条手机号的代价远大于少提交一份文档。

## 2. 命名规范

带日期的过程文档一律 `YYYY-MM-DD` 后缀 / 前缀，模块名大写：

| 类型 | 命名格式 | 示例 | 位置 |
|------|---------|------|------|
| 分析报告 | `<MODULE>_ANALYSIS_YYYY-MM-DD.md` | `QUIZ_ANALYSIS_2026-08-07.md` | `docs/reports/analysis/` |
| 修复报告 | `<MODULE>_FIX_YYYY-MM-DD.md` | `PATH_FIX_2026-08-07.md` | `docs/reports/fixes/` |
| 更新记录 | `<MODULE>_UPDATE_YYYY-MM-DD.md` | `BACKEND_UPDATE_2026-08-07.md` | `docs/reports/updates/` |
| 会话总结 | `SESSION_LOG_YYYY-MM-DD.md` | `SESSION_LOG_2026-08-07.md` | `docs/sessions/`（不入库） |
| 验证清单 | `VALIDATION_AFTER_<事件>_YYYY-MM-DD.md` | `VALIDATION_AFTER_QUIZ_2026-08-07.md` | `docs/validation/` |
| 开发日志 | `YYYY-MM-DD_<topic>.md` | `2026-08-07_path_audit.md` | `docs/logs/` |

常青文档（design / standards / roadmap）不带日期，用文档内「版本 + 最近更新」行记录修订。

## 3. 变更同步义务

改了什么，就必须更新什么——PR 自查清单：

| 代码变更 | 必须同步的文档 |
| --- | --- |
| API 契约（IPC 通道 / NDJSON 事件 / CLI 参数） | `docs/design/api.md` + `frontend/docs/API_SPEC.md` |
| 架构 / 模块边界 / 目录结构 | `docs/design/architecture.md` + `docs/standards/directory.md` + 根 `README.md` 结构图 |
| 新增平台能力 | `README.md` 平台支持矩阵 + `docs/roadmap/` 对应文档 |
| 用户可见行为 / 配置项 | 根 `README.md` + `backend/README.md` / `frontend/README.md` |
| 重要修复 | `docs/reports/fixes/` 报告 + `docs/validation/` 清单 + `docs/changelog/CHANGELOG.md` |
| 协作流程 / 规范本身 | `CONTRIBUTING.md` / `AGENTS.md` / `docs/standards/` |

## 4. CHANGELOG 条目格式

`docs/changelog/CHANGELOG.md` 按版本倒序，条目一行一事：

```markdown
## [YYYY-MM-DD] <版本或主题>
- **feat**: 描述（关联 Issue/PR 编号，如 #12）
- **fix**: 描述
```

跨版本的历史变更整文件移入 `docs/changelog/archive/`，主文件只保留近期版本。

## 5. 文档写作约定

- 语言：中文为主，代码 / 标识符 / 协议字段保留英文。
- 每个目录至多一个 `README.md` 作为入口；`docs/README.md` 是文档中心唯一索引，新增子目录或重要文档时同步登记。
- 引用本地文件用相对路径链接；引用 Issue / PR 用 `#N`。
- 示例中的账号 / 手机号 / 密钥一律使用 `13200003918`、`password: example`、`sk-example-xxx` 这类明显的占位形式，**禁止用任何真实值**（含「看起来像示例的本人账号」）。
