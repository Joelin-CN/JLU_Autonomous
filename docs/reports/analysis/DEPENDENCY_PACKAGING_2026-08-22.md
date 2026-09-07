# 依赖体检与打包路线分析（2026-08-22）

目的：盘点当前依赖健康度，回答"以后怎么打包分发"。全部数据为当日实测。

## 一、依赖体检

### Python 后端 — 健康

| 环境 | pip check | 关键包 |
|---|---|---|
| conda `chaoxing-backend`（开发/余额） | ✅ 无冲突 | openai 2.53.0、volcengine-python-sdk 5.0.44、pytest 9.1.1 |
| PATH Python 3.13（默认运行时） | ✅ 无冲突 | openai 2.43.0 |

- 运行时声明（requirements.txt）：openai（必需）+ volcengine-python-sdk（仅余额），均为 `>=` 开区间，**无锁文件** —— 新机器安装会拿到最新版，理论上存在破坏性更新的复现风险。
- dev 依赖已单独声明（requirements-dev.txt：pytest、pillow）。
- 核心链路零第三方依赖（浏览器走外部 playwright-cli），主链路对 Python 环境要求极低。

### npm 前端 — 两类问题

**漏洞（npm audit）**：
- 全链 18 个（2 critical / 14 high / 2 moderate），其中 16 个在**构建工具链**（electron-builder 24 → tar/extract-zip/electron-updater 链、vite 5 → esbuild dev-server 等），不进最终产物但影响构建机；
- 生产依赖链 2 个 high：nanoid、postcss（vite 构建管线拓扑进 prod 树，实际只在构建期使用，asar 内只有 vue/pinia 等运行时包）；`npm audit fix`（非 force）可修。

**版本时效（落后幅度大）**：

| 包 | 当前 | 最新 | 说明 |
|---|---|---|---|
| electron | 28.3.3 | 43.4.1 | 落后 15 个大版本（Chromium 120），安全补丁窗口是主要风险 |
| vite | 5.4.21 | 8.2.2 | 构建链 |
| electron-builder | 24.13.3 | 26.15.3 | 升级可消掉大部分 dev 漏洞 |
| pinia / typescript / vitest / vue-router / @vueuse | 2/5.9/1.6/4.6/10 | 4/7/4.1/5.2/14.4 | 均 semver-major 落后，非急迫 |

### 外部系统依赖（用户机器必须自备）

| 依赖 | 现状 | 缺失时表现 |
|---|---|---|
| Python 3.10+ | 不随包分发 | 启动任务/各 CLI 中文报错 + 设置页行内校验（2026-08-22 修复） |
| Node.js + playwright-cli（0.1.14，全局 npm） | 不随包 | 后端中文安装指引（同日修复） |
| Google Chrome（系统安装） | 不随包 | playwright-cli open 失败（rc≠0 日志，无专门引导） |
| AI 凭证 doubao.txt / 账号 chaoxing.txt | data/passwords 手动 | 后端报"无凭证" |

## 二、打包现状（当日核验）

- 流程：`vite build`（渲染层 3.4MB）→ `vite build --mode electron`（主进程 256KB）→ `electron-builder`（NSIS x64）。
- 白名单 extraResources：`chaoxing/` 源码 + `chaoxing_config.example.json` + `.playwright/cli.config.json` + `scripts/` 3 资产 + requirements.txt —— 真实配置/密码/档案不入包（已实测）。
- 体积：安装包 76MB / 解压 281MB（Electron 运行时是大头）/ `resources/backend` 8MB / app.asar 16.9MB（vue+pinia 全量 node_modules，含 148 个 .map 可剔除）。
- 未配置：自动更新（electron-updater/publish）、便携版（portable target）、CI 构建。

## 三、以后怎么打包 —— 三档方案

### A. 现状 + 引导完善（近期，零成本）✅ 已基本就绪
用户自装 Python/Node/playwright-cli/Chrome；缺失报错今天已全部中文化并带指引。
适用：自用、小范围给会用命令行的人。**无需新工程，保持现状即可。**

### B. 半自包含（中期，推荐目标）—— 消掉 Node/playwright-cli 依赖
- **捆绑 playwright-cli**：把 `@playwright/cli` 及其 node_modules 打进 extraResources，用 Electron 自带的 Node 运行时执行（`process.execPath --run-as-node`），后端 `playwright_cli` 配置项指向该入口（env `CHAOXING_PLAYWRIGHT_CLI` 下发）。改动集中在 engine.py/auth.py 的 cli 解析 + electron-builder 白名单，工程量中等。
- （可选）**捆绑便携 Python**：python-build-standalone / PyInstaller onefiledir 把后端 + openai 打进 extraResources（+80~150MB），用户免装 Python；ai.handler/pythonBridge 的解析顺序加"内置解释器优先"。设置页保留覆盖入口。
- Chrome 仍用系统安装（打包自带 Chromium 需 +130MB 且 license/更新负担大，不推荐）。

### C. 全自包含（远期，仅当要公开分发）
B + 自带 Chromium + 自动更新（electron-updater + GitHub publish，NSIS blockmap 差分更新已天然支持）。体积 400MB+，维护成本最高。

### 无论哪档都建议先做（小步、低风险）

1. `npm audit fix`（非 force，修 nanoid/postcss 等）；
2. electron-builder 24 → 26（消掉 tar/extract-zip/electron-updater 漏洞链），跑一次完整打包回归；
3. electron-builder 配置补 `artifactName` 规范命名 + `compression: maximum`；asar 白名单排除 `*.map`（148 个 sourcemap）；
4. Python 侧加锁：`pip freeze > requirements.lock`（或迁移 uv），README 注明部署用锁安装；
5. Electron 28 → 36+ 分步升级计划（每步跑 595 单测 + 实机回归；这是独立工程，建议单开任务）。

## 四、结论

依赖本身健康（Python 双环境零冲突、核心链路低依赖），主要欠账在 **npm 构建链的版本与漏洞**、**无 Python 锁文件**、以及**用户机器四项外部依赖**。打包路线建议：近期维持 A（已就绪），把 B 的"捆绑 playwright-cli"作为下一个打包专项，C 仅在需要公开分发时考虑。

---
*附：命令快照 —— `npm outdated`（13 项 major 落后）、`npm audit`（18/2high-prod）、`pip check`（双环境通过）、体积实测（76MB/281MB/8MB/16.9MB）。*
