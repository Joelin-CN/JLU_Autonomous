# 贡献与协作规范

本仓库由双管理者 **@Joelin-CN** 与 **@Arthur-Pendrag0n** 异步维护。两人时区 / 作息 / 在线时段不保证重合，因此一切协作以「留下可追溯记录」为第一原则：宁可多写一行 Issue / PR 评论，不依赖实时沟通。

AI 代理（Codex / Claude 等）参与开发时同样遵守本规范，见 [AGENTS.md](AGENTS.md)。

---

## 1. 分支模型

```text
main                  # 始终可运行，受保护：只接受 PR 合并，禁止直推
└── feature/<topic>   # 一个分支只做一件事，命名用英文小写连字符
└── fix/<topic>
└── docs/<topic>
```

- **分支命名**：`feature/zhihuishu-login`、`fix/quiz-retry-loop`、`docs/api-update`。平台相关功能建议带平台前缀（如 `feature/zhihuishu-xxx`、`feature/chaoxing-xxx`）。
- **生命周期短**：分支存活以天计；长期分支（>1 周）应在 PR 描述说明原因，或拆小。
- **保持新鲜**：合并前 rebase 或 merge 最新 `main`，冲突由分支作者解决。

## 2. 提交约定（Conventional Commits）

```text
<type>: <简短中文描述>

[可选正文：动机 / 方案 / 影响]
```

| type | 用途 |
|------|------|
| `feat` | 新功能（如 `feat: 智慧树账号登录`） |
| `fix` | 缺陷修复 |
| `docs` | 仅文档变更 |
| `chore` | 构建 / 配置 / 依赖 / 仓库杂务 |
| `refactor` | 既非新功能也非修复的重构 |
| `test` | 仅测试变更 |

- 一个提交只做一件事；大 PR 拆成多个语义清晰的提交。
- 提交前 `git status` 确认没有混入无关文件；`data/`、`references/` 内容与任何凭据**永远不得入库**。

## 3. PR 流程

1. 从最新 `main` 拉分支开发；
2. 推送后开 PR，套用 PR 模板（变更说明 / 自验结果 / 影响面）；
3. CODEOWNERS 会自动请求另一位管理者 review；**至少 1 位管理者批准**后方可合并；
4. CI 必须绿（后端单测 + 前端类型检查与测试）；红了先修再请求 review；
5. 合并方式：默认 **Squash and merge**（保持 main 历史线性）；确需保留多提交结构时用 Rebase and merge；
6. 合并后由分支作者删除远端分支。

**异步守则**：

- review 不设时限，但看到请尽快；超过 72 小时未响应，可在 PR 中 `@` 对方一次。
- 对方 PR 中的讨论以 PR 评论为准，达成一致的结论要落在评论里，不做口头 / 群内君子协定。
- 涉及 API 契约、架构、跨平台抽象的 PR，另一位管理者的 review 为**必选**而非可选。
- 需求类 Issue 开发前先 `assign` 自己，PR 描述关联 Issue（`Closes #N`），避免两人撞车。

## 4. 刷课需求流转（Issue 认领制）

两位管理者异步处理「刷课需求」，统一走 GitHub Issue，规则如下：

| 阶段 | 动作 |
|------|------|
| 提交 | 用 **「刷课需求」** Issue 模板建单（需求方或管理者代建均可），标 `brush-request` + `status/pending` |
| 认领 | 管理者把自己的 GitHub 账号设为 **assignee**，标签改 `status/in-progress`；**已有 assignee 的需求单不得重复接手** |
| 执行 | 进展与异常（验证码 / 账号风控 / 平台改版）以评论追加在 Issue 内 |
| 完成 | 结果（完成科目 / 遇留问题）评论收尾，关闭 Issue，标签改 `status/done` |

平台标签：`platform/chaoxing`、`platform/zhihuishu`（按需建）。

> **隐私红线（公开仓库）**：Issue / PR / 评论对全网可见。**严禁**在 Issue 中出现账号手机号、密码、验证码、真实姓名、API Key 等任何凭据或个人信息——账号凭据一律线下交给接单管理者，Issue 内只记录课程名 / 诉求 / 进度。详见 [SECURITY.md](SECURITY.md) 与 [docs/standards/secrets.md](docs/standards/secrets.md)。

## 5. 开发验证要求

- 后端：`python -m pytest tests/unit -q -s`（在 `backend/` 下，conda 环境 `chaoxing-backend`）；
- 前端：`npm run typecheck` 与 `npm test`（在 `frontend/` 下）；
- CI（`.github/workflows/ci.yml`）在每次 push / PR 自动执行上述检查，作为合并门槛；
- 涉及接口或架构变更时，先同步 `docs/design/` 对应文档再开 PR；重要修复按 [docs/standards/documents.md](docs/standards/documents.md) 补报告与验证清单。

## 6. 目录与文件规范

新增 / 移动文件前先读 [docs/standards/directory.md](docs/standards/directory.md)（什么放哪里）与 [docs/standards/documents.md](docs/standards/documents.md)（文档怎么命名归档）。摘要：

- 代码：`frontend/`、`backend/`，多平台演进的目标布局见 directory.md（当前为超星单平台布局，重构在智慧树开发期进行）；
- 运行时数据：仓库根 `data/`（git 忽略）；
- 文档：`docs/` 下按类型归位，命名带 `YYYY-MM-DD` 日期前缀。

---

**版本**: 1.0（2026-09-07，随仓库打底建立）
