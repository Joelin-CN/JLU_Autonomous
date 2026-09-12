# 目录规范

> 什么内容放在哪里。新增 / 移动任何文件前先读本文。配套：[documents.md](documents.md)（文档命名与归档）、[secrets.md](secrets.md)（凭据红线）。
>
> 版本 1.0 · 2026-09-07（随仓库打底建立）

---

## 1. 顶层职责表（现状）

| 目录 / 文件 | 职责 | 入库 |
| --- | --- | --- |
| `frontend/` | Electron + Vue 3 桌面端（`electron/` 主进程、`src/` 渲染进程、`src/shared/` 共享层） | ✅ 源码入库；`node_modules/`、`dist*`、`release/` 忽略 |
| `backend/` | Python 后端（`chaoxing/` 包、`scripts/`、`tests/`、CLI 启动器） | ✅ 源码与测试入库；运行时产物忽略 |
| `data/` | 运行时数据（凭据 / 浏览器档案 / 输出 / 日志 / 截图） | ❌ 仅 `data/README.md` 入库 |
| `references/` | 第三方参考脚本，只读 | ❌ 仅 `references/README.md` 入库 |
| `docs/` | 文档中心（见 [documents.md](documents.md)） | 部分入库（sessions 等内部目录忽略） |
| `.github/` | CI 工作流、Issue / PR 模板、CODEOWNERS | ✅ |
| `.claude/` | 项目级 AI 代理技能 | ✅（`plans/`、锁文件忽略） |
| 根部 `README.md` / `CONTRIBUTING.md` / `SECURITY.md` / `AGENTS.md` / `LICENSE` | 项目门面与协作规范 | ✅ |

## 2. 落位规则

新文件按以下顺序判断归属：

1. **是运行时产生的吗**（日志 / 截图 / 输出 / 缓存 / 浏览器档案）→ 一律 `data/` 对应子目录或各项目的忽略目录，**永不入库**。
2. **是凭据或含个人信息吗** → `data/passwords/`，线下传递，**永不入库**（详见 [secrets.md](secrets.md)）。
3. **是代码 / 测试 / 构建配置吗** → `frontend/` 或 `backend/`；测试紧邻被测模块（后端在 `backend/tests/`，前端 `*.test.ts` 与被测文件同目录）。
4. **是文档吗** → 按 [documents.md](documents.md) 的分类表归位到 `docs/` 对应子目录。
5. **是仓库级配置吗**（CI / 模板 / git 配置） → `.github/` 或仓库根。
6. 都不是 → 先在 PR 里说明理由，不要新建顶层目录。**顶层目录的增删属于架构决策**，需双管理者一致同意。

## 3. 多平台布局（M1 已实施）

仓库已完成平台并列布局（2026-09-12，M1 平台抽象重构，见 `docs/roadmap/zhihuishu.md`）：

```text
backend/
├── core/                  # 平台无关：JSON-line 协议 / 编排基础设施 / 浏览器引擎 / AI 路由 / 内存治理
│   ├── constants / config / session / logging_setup / memory / tracking / utils / exceptions
│   ├── browser/           # engine / js_runner / viewport / orphans（按 profile 的孤儿 Chrome 清扫）
│   └── ai/                # doubao / deepseek / router / billing（平台无关）
├── platforms/
│   ├── chaoxing/          # 超星平台实现（原 chaoxing/ 平台相关部分迁入；platform/ solvers/ font/ js/ data/ + api/orchestrator/discover/子入口）
│   └── zhihuishu/         # 智慧树平台实现（M2 起建设）
├── chaoxing/              # 兼容垫片：sys.modules 别名表 + 5 个 CLI 入口自替换转发（保 python -m chaoxing.* 旧命令）
└── tests/
    ├── unit/  integration/  e2e/
    └── platforms/         # 按平台组织的测试镜像 platforms/ 结构
```

- 平台模块实现统一的平台能力面（登录态 / 课程扫描 / 章节处理 / 测验求解）；接口定义与拆分方案见 [docs/roadmap/zhihuishu.md](../roadmap/zhihuishu.md) 与 `docs/design/`。
- **环境变量兼容**：`CHAOXING_WORKSPACE` / `CHAOXING_DATA_DIR` 等前缀名在 core 中沿用（历史约定，双平台共享）；平台专属 HEADED 开关支持 `{PLATFORM}_HEADED`（如 `ZHIHUISHU_HEADED`），`CHAOXING_HEADED` 对全平台生效。
- **重构约束**：目录搬迁与 import 修复一次 PR 内完成并保持测试绿；不允许「先搬一半」的中间态合并进 `main`。
- 前端 `frontend/` 保持平台无关：平台差异收纳在后端协议与数据模型内，前端不感知平台实现细节。

## 4. 禁止事项

- 禁止在代码 / 文档 / 配置中出现绝对盘符路径（用 `chaoxing/constants.py` 常量或环境变量，见 [AGENTS.md](../../AGENTS.md) 路径约定）。
- 禁止把 `data/`、`references/` 的内容以任何形式（复制 / 截图 / 引用路径列表）提交入库。
- 禁止在 `frontend/` 与 `backend/` 之外新建代码目录。
- 空目录不入库（git 不支持）；需要占位时放一个说明用途的 `README.md`。
