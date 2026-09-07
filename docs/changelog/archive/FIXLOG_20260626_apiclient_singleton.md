# 修复日志 — API 客户端单例化（前端内存管理）

**日期**: 2026-06-26
**范围**: `frontend/src/shared/lib/apiClient.ts`
**类型**: 前端内存泄漏修复（不改动前后端通讯 API）

---

## 一、问题来源

修复日志 `console-2026-06-24T16-58-10-962Z.log` 中，单次页面加载出现 **5 条以上** 的：

```
[INFO] [Chaoxing] Running in browser mode — using MockApiClient @ .../apiClient.ts:6
```

且每次 HMR 热重载（`apiClient.ts?t=...`）后又重复 5 次。

## 二、根因（确认为前端自身造成）

`createApiClient()` 不是单例：每次调用都 `new` 一个客户端。而 **5 个 Pinia store 各自在模块顶层调用了一次**：

- `account.store.ts`
- `attention.store.ts`
- `course.store.ts`
- `execution.store.ts`
- `settings.store.ts`

→ 一次加载产生 **5 个客户端实例**，与日志里的 5 条输出精确对应。

内存影响：

| 模式 | 后果 |
|------|------|
| Mock | 每个实例构造时生成 mock 数据（账号/课程/工单）→ 数据集 5 份复制；各自持有独立的 `listeners` Map 与 `currentSimulation` 定时器链 |
| Electron | 每个实例都可独立注册 IPC 监听器（`cleanupFns`） |
| 通用 | 每次 store 模块被 HMR 重新求值，又叠加新实例，旧实例不释放 |

这是前端代码自身的内存管理缺陷，**与后端无关**。

## 三、修复

将 `createApiClient()` 改为 **模块级单例（memoize）**：首次调用创建，后续调用返回同一实例。新增 `resetApiClient()` 用于测试/完整销毁。

- 前后端通讯 API 接口（IPC 通道、`ChaoxingApi` 接口）**完全未改**。
- 5 个 store 的 `import { createApiClient }` 调用点无需改动，自动共享同一实例。
- 安全性核查：只有 `execution.store` 注册事件监听（`on*`）并调用 `api.dispose()`；其余 4 个 store 仅调用请求类方法。共享单例后 `dispose()` 仅影响 execution 自己注册的监听，对其他 store 无副作用。

## 四、效果

- 客户端实例数：5 → **1**
- 消除 mock 数据集的 4 份冗余复制
- 消除冗余监听器 Map / 模拟定时器链
- 消除日志刷屏（每次加载从 5 条降为 1 条）

## 五、验证

- `npm run typecheck`（两遍 vue-tsc）：✅ 通过
- `npm run build:web`：✅ 通过（836ms）

## 六、修改文件

```
frontend/src/shared/lib/apiClient.ts  — createApiClient 单例化 + 新增 resetApiClient
```
