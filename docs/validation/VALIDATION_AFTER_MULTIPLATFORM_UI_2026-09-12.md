# 多平台 UI 重构验证清单（2026-09-12）

> 对应 PR：`refactor(frontend): 多平台 UI 重构`（feature/renderer-platform-ui）。
> 方法：`npm run dev`（纯 Web / MockApiClient）→ browser-use `domSnapshot()` DOM 确认 → 截图 + vision 分析视觉确认。两证据源不一致时以视觉实况为准（本轮未出现不一致）。

## P0（必须）— 全部通过 ✅

| # | 验证项 | DOM 证据 | 视觉证据 | 结果 |
|---|--------|----------|----------|------|
| 1 | 品牌通用化：侧栏/头部「JLU 学习助手」，无「超星助手」残留 | heading "JLU 学习助手"；grep 品牌字样仅剩平台名与后端契约 | 01-dashboard.png：品牌区层级清晰 | ✅ |
| 2 | 全局平台切换器（侧栏品牌区下方，运行中禁切） | `tablist "课程平台"`：tab 📘 超星 [selected] / 🌳 智慧树 | 01/02：选中态蓝色/绿色边框可辨 | ✅ |
| 3 | 切换平台 → 账号列表按平台分桶切换（PR #3 断点修复） | 智慧树选中后左栏 `账号列表 🌳 智慧树 0/3`、账号为学号 `202****9954`（此前因 loaded 缓存早退 + handler 硬编码 chaoxing 切不动） | 02-course-atlas-zhihuishu.png：绿色主题统一、学号掩码正常 | ✅ |
| 4 | 课程数据按平台分桶（复合键防撞） | 智慧树课程卡与超星课程互不串（两次快照课程集不同） | 同上截图 | ✅ |
| 5 | 能力矩阵：智慧树「全自动（视频）」文案 + 仅刷题/仅内容置灰带理由 | 按钮状态 `{text:仅刷题, enabled:false, title:"智慧树答题求解（M4）开发中…"}`、`{仅内容, false, "…请使用「全自动（视频）」"}` | （状态验证，DOM 充分） | ✅ |
| 6 | 工单·扫码型：二维码+per-ticket 倒计时+无输入框 | title 智慧树扫码登录；timer `⏳ 03:00`（timeoutSeconds=180 生效，非硬编码 10min）；hasInput=false；按钮=取消等待 | 03-qr-modal.png：二维码居中、遮罩层级正常 | ✅ |
| 7 | 工单·提示型：文字指引+申诉链接 linkify | message 含可点击 `a[href="https://onlineweb.zhihuishu.com/appeal"]`；无输入框 | （DOM 充分） | ✅ |
| 8 | 工单·输入型（超星，现状回归） | `__popCaptcha()` 输入型注入 → 图片+输入框+提交/跳过（mock 任务 4s 后自动弹超星验证码同验证） | 既有形态，回归通过 | ✅ |
| 9 | 设置页账号管理：平台 Tab + 字段按能力矩阵裁剪 | 智慧树表头 `[#, 账号, 操作]`（无登录网址列）+ 扫码提示；超星表头含「登录网址」；两平台账号独立增删 | （DOM 充分） | ✅ |
| 10 | 平台上下文持久化 + localStorage 迁移 | 刷新后 `storedPlatform=zhihuishu`、chip 仍智慧树；旧 key `chaoxing-assistant-settings` 已删除（读旧写新） | — | ✅ |
| 11 | typecheck / vitest | `vue-tsc` 双 project 零错误；**31 passed**（新增 5 组：platforms 注册表 / classifyTicketKind / settings 迁移 / captcha 超时 / mock 平台路由） | — | ✅ |
| 12 | 后端不回归 | `conda run chaoxing-backend pytest tests/unit -q -s` exit 0 | — | ✅ |

## P1（重要）

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 关注队列：平台过滤 pill（全部/紧急/警告/信息 ‖ 全平台/超星/智慧树）+ 工单平台 tag + 申诉链接可点击 | ✅ DOM+04 截图 vision |
| 2 | 仪表盘按平台分组：统计卡分解小字（超星 8 · 智慧树 3）+ 点阵双平台分块 + AI 余额卡保留全局 | ✅ DOM+01 截图 vision |
| 3 | 执行页 banner 平台徽标 + 泳道账号名按任务平台取桶 | ✅（typecheck + 空态快照；运行态走 mock 任务链路已由 store 测试覆盖） |
| 4 | electron 主进程最小修复只动 handler 内部（通道名/协议未变） | ✅ diff 审查：`IPC_CHANNELS` 与 NDJSON 事件类型零改动 |

## P2（可选 / 存量观察项，非本次引入）

- 仪表盘点阵图例色与状态色感知差异（存量配色）；统计卡第二行不满（存量 5 列 6 卡布局）。
- 「已选 0/3」计数器首眼看可能误读（存量交互）。
- 工单平台 tag 建议加平台图标、申诉链接建议加 hover/按钮化（vision 建议，增强级）。
- 图标 `build/icon.ico` 沿用旧品牌（无设计资源，PR 中注明后续替换）。

## 截图索引（data/screenshots/ui-refactor/，不入库）

- `01-dashboard.png` — 仪表盘（品牌/切换器/双平台统计）
- `02-course-atlas-zhihuishu.png` — 课程总览·智慧树上下文（断点修复证据）
- `03-qr-modal.png` — 扫码登录工单弹窗
- `04-attention-queue.png` — 关注队列（平台过滤与工单 tag）
