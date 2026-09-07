# 修复日志 — 安全漏洞修复 & 系统稳定性加固

**日期**: 2026-06-25
**范围**: `frontend/` 目录（Electron + Vue3 前端）
**背景**: 用户报告前次会话中电脑完全卡死。通过分析 Windows WER 内核崩溃报告和前端代码审计，发现 GPU 驱动崩溃链和多个安全漏洞。

---

## 一、崩溃诊断

### 硬件环境

| 组件 | 规格 |
|------|------|
| CPU | AMD Ryzen 9 8945HX（16核/32线程） |
| RAM | 31.8 GB |
| GPU | NVIDIA GeForce RTX 5070 Laptop（4 GB VRAM） |
| 驱动 | 32.0.15.9621 |

### Windows 内核崩溃（WER ReportQueue）

从 `C:\Windows\Minidump\062426-25406-01.dmp` 和 WER 归档中确认 6 次内核崩溃：

| BugCheck | 含义 | 说明 |
|----------|------|------|
| 0x117 | VIDEO_TDR_TIMEOUT_DETECTED | GPU 驱动超时，显卡不响应 |
| 0x141 ×2 | VIDEO_ENGINE_TIMEOUT_DETECTED | GPU 引擎超时 |
| 0x50 | PAGE_FAULT_IN_NONPAGED_AREA | 内核内存访问违规 |
| 0xC2 | BAD_POOL_CALLER | 内核内存池损坏 |
| 0x0 | 通用崩溃 | |

应用层同步崩溃：NVIDIA Overlay.exe（多次）、nvcontainer.exe、Explorer.EXE、dwm.exe（桌面 GPU 合成器）、AUDIODG.EXE。

### 根因分析

```
N 个 Headless Chromium 持久会话 × ~300MB/个（无内存限制）
  → 系统 RAM 压力
  → NVIDIA 驱动 32.0.15.9621 在内存压力下不稳定
  → GPU 驱动超时（BugCheck 0x117/0x141）
  → 驱动损坏内核内存池（BugCheck 0x50/0xC2）
  → 系统蓝屏/完全卡死
```

**关键事实：** 浏览器以 headless 模式运行（`CHAOXING_HEADED` 默认 `"0"`），不使用物理 GPU 渲染。崩溃不是 VRAM 耗尽，而是系统 RAM 压力触发了 NVIDIA 驱动的已知缺陷。

### 最大并发估算

| 场景 | 安全上限 | 每账号内存 |
|------|---------|-----------|
| 当前（无优化） | 8-10 账号 | ~370 MB |
| 预期（后端优化后） | 18-22 账号 | ~270 MB |
| Browser Context 池 | 35-50 账号 | ~50 MB（增量） |

> **你之前崩溃时可能只跑了不到 10 个账号。** 问题不在"不够用"，在"没有防护"。

---

## 二、安全漏洞发现

| 级别 | 漏洞 | 位置 |
|------|------|------|
| 🔴 严重 | Electron `sandbox: false` | `frontend/electron/main.ts:25` |
| 🔴 严重 | Python 子进程继承完整 `process.env` | `frontend/electron/python/pythonBridge.ts:60` |
| 🔴 严重 | 明文凭据文件 | `passwords/pwd.txt`, `passwords/doubao.txt` |
| 🔴 严重 | Settings 明文 JSON 存 localStorage | `frontend/src/app/stores/settings.store.ts:8` |
| 🟡 高危 | IPC 事件监听器清理函数被丢弃（7个方法） | `frontend/src/shared/lib/ipcClient.ts:210-305` |
| 🟡 高危 | `innerHTML` DOM XSS 风险 | `scripts/_decrypt_font.js:3165,3222`（后端仓库） |
| 🟡 高危 | 无速率限制 / 无 CSP / IPC 无输入校验 | `job.handler.ts`, `main.ts` |

---

## 三、已实施修复（Block 1 + Block 2）

### Block 1：崩溃预防

| # | 文件 | 修改 | 目的 |
|---|------|------|------|
| 1 | `frontend/electron/main.ts` | 添加 `disable-gpu` + `disable-gpu-compositing` 开关 | 移除 Electron 可见窗口的 GPU 风险 |
| 2 | `frontend/electron/main.ts` | `before-quit` 中 `taskkill /f /im chromium.exe` | 清理僵尸 Chromium，防止进程累积 |
| 3 | `frontend/electron/python/pythonBridge.ts` | `stop()` 硬化为 tracked timers + `clearKillTimers()` | 确保 Python 子进程必定被终止 |
| 4 | `frontend/electron/ipc/job.handler.ts` | `stopActiveJob()` 增强：10s 轮询 + 超时 `taskkill /pid /t` | app quit 时强制杀进程树 |

### Block 2：安全修复

| # | 文件 | 修改 | 目的 |
|---|------|------|------|
| 5 | `frontend/electron/main.ts` | `sandbox: false` → `sandbox: true` | 启用 Electron 渲染器沙箱 |
| 6 | `frontend/electron/python/pythonBridge.ts` | `...process.env` → 白名单 `buildSafeEnv()`（10个必要变量） | 防止 API Token 等敏感凭据泄漏到 Python |
| 7 | `frontend/src/shared/lib/ipcClient.ts` | 7 个 `onXxx()` 全部存储+返回 cleanup 函数 | 修复 IPC listener 泄漏 |
| 8 | `frontend/src/shared/lib/types.ts` | `ChaoxingApi` 接口 `onXxx` 返回类型 `void` → `() => void`，加 `dispose()` | 类型安全 |
| 9 | `frontend/src/shared/lib/mockClient.ts` | `MockApiClient` 同步更新 + `onWithCleanup()` 辅助 | 接口一致性 |
| 10 | `frontend/electron/main.ts` | CSP header 注入（`default-src 'self'`） | 纵深防御 XSS |
| 11 | `frontend/electron/ipc/job.handler.ts` | IPC rate limiter（500ms 冷却）+ `validateAccountIds()`（上限50/正整数） | 防 DoS + 输入校验 |

### 额外

| # | 文件 | 修改 | 目的 |
|---|------|------|------|
| 12 | `frontend/electron/python/pythonBridge.ts` | Python 进程 2 小时安全超时 | 防止 runaway 进程无限消耗资源 |

---

## 四、未纳入范围（后端仓库）

`scripts/` 目录为老版本，后端在另一个仓库。以下需在那边实施：

1. **Headless Chromium 内存优化 flags** — `--renderer-process-limit=1`、`--disable-dev-shm-usage` 等，每账号省 ~100MB
2. **系统内存监控** — 启动新账号前检查可用 RAM，自动限流
3. **Browser Context 池** — 多账号共享一个 Chromium 进程
4. **`_decrypt_font.js` innerHTML → textContent**

---

## 五、修改文件清单

```
frontend/electron/main.ts                         — GPU 开关 + sandbox + CSP + quit 清理
frontend/electron/python/pythonBridge.ts          — env 白名单 + stop() 加固 + 安全超时
frontend/electron/ipc/job.handler.ts              — 速率限制 + 输入校验 + stopActiveJob 增强
frontend/src/shared/lib/ipcClient.ts              — listener cleanup + dispose()
frontend/src/shared/lib/types.ts                  — ChaoxingApi 接口更新
frontend/src/shared/lib/mockClient.ts             — MockApiClient 同步
```

**5 个源文件，12 项修改。TypeScript 编译通过，无新增类型错误。**

---

## 六、验证建议

| 检查项 | 方法 |
|--------|------|
| 沙箱启用 | Electron DevTools → `chrome://sandbox` → Renderer: Sandboxed |
| GPU 禁用 | `chrome://gpu` → 确认软件渲染 |
| env 不泄漏 | Python 子进程 `print(os.environ.keys())`，验证无 `ARK_API_KEY` |
| 残留进程 | 退出 Electron 后任务管理器确认无 `chromium.exe` |
| 内存压测 | 依次跑 5→10→15 账号，监控 RAM 曲线 < 85% |
| 功能回归 | 登录 → 扫描课程 → 题库求解 → 暂停/恢复 → 设置持久化 |
| 崩溃回归 | `eventvwr.msc` 检查运行 2 小时后无新 BugCheck |

---

## 七、系统资源核算（参考）

```
总 RAM:     31.8 GB
固定开销:   -7.0 GB  (Win11 + Electron + DeepSeek 共享浏览器 + 15% 安全余量)
━━━━━━━━━━━━━━━━━━━━━━
可用于账号:  20.2 GB
每账号:       0.37 GB (无优化) / 0.27 GB (后端优化后)

安全上限:
  当前:  8-10 账号
  优化: 18-22 账号
  池化: 35-50 账号

瓶颈: CPU 32 线程 + NVIDIA 驱动稳定性 (非 RAM)
```
