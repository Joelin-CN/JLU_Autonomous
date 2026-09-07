# 变更日志 — 余额查询功能接入

**日期**: 2026-06-26
**范围**: `frontend/` 目录（Electron 主进程 + Vue3 渲染进程）
**类型**: 新功能（后端 v1.2 手册 §4.7 落地）
**背景**: 后端新版交互手册（v1.2）新增「余额查询子命令」一节，前端此前完全未接入——Dashboard 顶部余额卡片是硬编码 `¥ 326.50 / 总额 ¥ 500.00` 的假数据。本轮把该功能端到端接通，并把契约合并进权威 API 文档（升级到 v1.3）。

---

## 一、功能说明

余额查询（`python -m chaoxing.balance`）查询火山引擎（豆包）账户现金余额。关键特性：

- **与任务流程完全解耦**：不走 `--job-id/--accounts/--mode`，不发任务事件流，独立 spawn 一个进程，stdout 输出**单行 JSON** 后退出。
- **必须用 Anaconda 解释器**：依赖 `volcengine-python-sdk`，该 SDK 只装在 Anaconda 里，不能用任务用的 `pythonPath`。
- **凭证独立**：读 `passwords/volc_billing.txt`（火山账单 OpenAPI 的 AK/SK），与豆包推理的 `ARK_API_KEY` 是两套，不可混用。

---

## 二、已实施改动

### Block 1：Electron 主进程

| # | 文件 | 改动 |
|---|------|------|
| 1 | `electron/types.ts` | 新增 `BalanceResult` 接口（金额字段全 string）+ `BALANCE_QUERY: 'balance:query'` 通道常量 |
| 2 | `electron/ipc/balance.handler.ts`（新建） | spawn Anaconda 解释器跑 `-m chaoxing.balance`；解析**最后一条非空 stdout 行**为 JSON；`BALANCE` → resolve，`ERROR` / exit≠0 → reject（中文提示）；30s 超时；ENOENT 时提示设 `CHAOXING_BALANCE_PYTHON`；沿用 PythonBridge 的环境变量白名单（不泄漏 `ARK_API_KEY`） |
| 3 | `electron/main.ts` | 注册 `registerBalanceHandlers()` |
| 4 | `electron/preload.ts` | `ElectronAPI` 暴露 `getBalance(): Promise<BalanceResult>` |

### Block 2：渲染进程

| # | 文件 | 改动 |
|---|------|------|
| 5 | `src/shared/lib/types.ts` | 新增前端 `Balance` 接口（`checkedAt` 为 epoch ms）+ `ChaoxingApi.getBalance()` |
| 6 | `src/shared/lib/ipcClient.ts` | 实现 `getBalance()`：调用 `electronAPI.getBalance()`，把后端 ISO `checkedAt` 解析为 epoch ms，其余字段直通 |
| 7 | `src/shared/lib/mockClient.ts` | 实现 `getBalance()`：返回固定模拟余额（`¥326.50`），无网络请求，浏览器模式可独立调试 |
| 8 | `src/views/DashboardView.vue` | 删除硬编码 `¥326.50 / ¥500`；新增 `balance`/`balanceError`/`balanceLoading` 响应式状态 + `loadBalance()`，`onMounted` 内 fire-and-forget 触发（不混进 `Promise.all`，查询慢/失败不阻塞页面其余加载）；卡片显示「查询中…」/可用余额/「余额查询失败：<原因>」 |

---

## 三、关键设计决策

1. **Anaconda 路径可覆盖**：handler 默认 `E:/Softwares/Anaconda/python.exe`（手册原文路径），但读 `CHAOXING_BALANCE_PYTHON` 环境变量优先。换机器只改环境变量，不动代码。
2. **不阻塞 Dashboard**：余额查询用 `void loadBalance()` 独立触发。后端没装 SDK / 查询慢时，账号与课程加载照常进行。
3. **金额保留为 string**：直接透传后端的 `availableBalance`/`cashBalance` 等字符串，不转 number，避免浮点精度丢失。只有 `checkedAt` 做 ISO→epoch 转换。
4. **取最后一行 stdout**：手册保证 stdout 严格单行 JSON，但 handler 仍取「最后一条非空行」解析，对偶发杂行更鲁棒。
5. **「总额 ¥500」去掉**：后端无总额字段，原假数据移除。主数值用 `availableBalance`，副标题带 `cashBalance`。

---

## 四、文档更新

| 文件 | 变更 |
|------|------|
| `docs/api/FRONTEND_BACKEND_API.md` | v1.2 → **v1.3**：新增 §4.7 余额查询（后端 CLI 协议 + 前端已接入说明）；§2.3 新增 `getBalance()` 方法；§3.1 通道列表补 `JOB_RESOLVE_TICKET` + `BALANCE_QUERY`（16→18，计别名 20）；§9.2 改为「已实现/已修复」并记录 v1.3；附录 A 加 `balance.handler.ts`；附录 B 勾选余额子命令 |
| `README.md`（根） | 文档索引/通道清单补余额查询 |
| `frontend/README.md` | 目录结构补 `balance.handler.ts`，功能说明补余额卡片 |
| 根目录 `1.md` | **删除**（后端临时丢入的 v1.2 手册，内容已合并进权威文档） |

---

## 五、修改文件清单

```
electron/types.ts                       — BalanceResult + BALANCE_QUERY 通道
electron/ipc/balance.handler.ts         — 新建：Anaconda spawn + 单行 JSON 解析
electron/main.ts                        — 注册 balance handler
electron/preload.ts                     — 暴露 getBalance()
src/shared/lib/types.ts                 — Balance 类型 + ChaoxingApi.getBalance()
src/shared/lib/ipcClient.ts             — 真实 getBalance()（ISO→epoch）
src/shared/lib/mockClient.ts            — Mock getBalance()
src/views/DashboardView.vue             — 真实余额卡片，替换硬编码
```

**8 个源/配置文件 + 1 个新建 handler。**

---

## 六、验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 类型检查（两遍） | `npm run typecheck` | ✅ exit 0（vue-tsc 2.x，渲染 + Node 侧均通过） |
| Web dev 启动 | `npm run dev` | ✅ Vite ready，`/`、`main.ts`、`DashboardView.vue` 均 HTTP 200 |
| Mock 余额渲染 | 浏览器访问 `/dashboard` | ✅ 卡片显示 `¥ 326.50` + `doubao 可用余额（现金 ¥ 326.50）` |

> 真实余额（连火山引擎账单 API）需 `npm run dev:electron` + 装有 `volcengine-python-sdk` 的 Anaconda + `passwords/volc_billing.txt` 凭证，本轮未在真实环境验证（前端契约与 Mock 已验证）。

---

## 七、合并到后端仓库后的待办

- [ ] 后端实现 `chaoxing/balance.py` 模块（`python -m chaoxing.balance`），按 §4.7 输出单行 `BALANCE`/`ERROR` JSON
- [ ] 确认目标机器 Anaconda 路径，必要时统一用 `CHAOXING_BALANCE_PYTHON` 环境变量配置
- [ ] 放置 `passwords/volc_billing.txt`（已被 `.gitignore` 忽略）
- [ ] 真实环境端到端验证一次余额查询
