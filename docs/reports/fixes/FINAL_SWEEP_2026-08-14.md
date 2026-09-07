# 收尾核查：Chrome 残留 / 0-0 课程语义 / 后端改动逐步骤识图

日期：2026-08-14（晚）

## 一、Chrome 进程残留

### 现象
- 停止所有账号任务后，`chaoxing-chrome-0` 会话仍处于 open，chrome.exe 主进程 +
  crashpad/gpu/network/storage/renderer 子进程全部残留（均绑定
  `data/chrome-profiles/account-0`）。
- 历史上多次出现“任务都结束了，Chrome 还在任务管理器里”。

### 根因
1. Electron `closeBrowserSessions()` 用 `execFile` 调用 `playwright-cli.cmd`，
   Windows 下 .cmd 必须 `shell:true`，否则关闭命令静默失败。
2. 前端 STOP 流程在 Python 未跑到 finally 时会 taskkill Python，
   后端 `close_chaoxing_browser()` 被跳过，只剩 Electron 兜底，而兜底又是失效的。
3. playwright-cli daemon 自身不会因会话关闭失败而回收 Chrome 树。

### 修复
- `frontend/electron/ipc/job.handler.ts`：`closeBrowserSessions` 改为
  `{ shell: true }` 执行 `.cmd`；3 秒后再用 PowerShell 定向清理
  `data/chrome-profiles` 下残留的 chrome.exe（按命令行过滤 profile 根，
  绝不碰用户自己的 Chrome）。
- `backend/chaoxing/platform/auth.py`：`close_chaoxing_browser` 改为
  `shell=True` 执行 close，关闭后等待 1s 并调用新增 `_kill_orphaned_chrome()`
  兜底；`ensure_chaoxing_browser` 打开前也会先清扫该账号 profile 的孤儿进程。

### 验证（真实端到端）
- 应用内启动 3 账号扫描任务 → 停止 → 15s 后：`playwright-cli list` 为空、
  chrome.exe 进程数 = 0。
- 直接调用 `close_chaoxing_browser(0)`：会话关闭、chrome.exe = 0。

## 二、“0 章节 / 0 已完成”课程语义

### 调研方法
- DOM：对多门 0/0 课程真实打开章节树扫描；
- 识图：对“2024年单片机竞赛基本技能比赛”课程页截图做视觉确认。

### 结论：0/0 有三种真实含义
1. **确实无任务点**（单片机竞赛、工程伦理、综合英语、C语言）：章节页
   “已完成任务点 0/0 + 暂无章节内容”，显示 0 章节 0 已完成是**正确的**。
2. **实际已完成但卡片没解析出进度**（大学物理ABC（上））：真实章节树
   103/103、27 个内容节；卡片只显示 0/0 → 之前被误当“未完成空课程”。
3. **有任务但卡片没解析出进度**（概率论、综合英语-2025、计算机体系结构、
   西班牙语2）：真实数据为 79/100、0/79、21 内容节、5 内容节等。

根因：`scan_courses` 从课程卡片解析“任务点进度”，部分卡片首屏未渲染该信息；
`discover_courses` 对 0/0 且无配置的课程**跳过真实章节扫描**，直接生成空配置。

### 修复
- `backend/chaoxing/discover.py`：0/0 课程也执行真实章节树扫描；
  - 扫描后 `done >= total > 0` → 判定“已完成”，从工作列表剔除；
  - 扫描失败 → 保留占位（可重试）；
  - 真空 0/0 → 正常保留为 0 章节。

### 验证（真实扫描）
- 修复后 account-0 发现 10 门课：大学物理ABC（上）被正确剔除（103/103）；
  概率论 79/100（16 测验 + 39 内容 + 9 章）、综合英语-2025 0/79（20 内容 + 5 章）、
  计算机体系结构 21 内容 + 7 章、西班牙语2 5 内容 + 1 章 均恢复真实数据；
  真空课程保持 0/0。
- 识图确认“2024年单片机竞赛基本技能比赛”：暂无章节内容、已完成任务点 0/0。

## 三、后端改动逐步骤识图核查

真实账号逐步执行后端主要链路，每步截图后用 vision 识图：

| 步骤 | 操作 | 识图确认 |
|------|------|----------|
| 1 | 登录（条件等待跳转） | 已登录个人空间（重庆邮电大学 林琦沅），进入个人空间成功 |
| 2 | 课程列表扫描（懒加载稳定） | 「我学的课」列表正常，大学物理ABC（下）任务点 60/88 68% |
| 3 | 章节树扫描 | 大学物理ABC（下）章节页，已完成任务点 60/88，目录列出章节课时 |
| 4 | 打开内容小节（grade-only 不完成） | 视频播放器与任务点信息正常显示；该小节含 2 个任务点（1 已完成 + 1 未完成，DOM done=1/notDone=1），目录“1”与头部“已完成”是同一小节多任务点的正常表现 |
| 5 | 仅刷题：真实填答 + AI 评分（不提交） | 答题页 27–30 题已选中答案（蓝色标记），无提交/交卷按钮被点击；第 1 题单选题已作答 |

第 5 步后端日志佐证：30 题、6 批 Doubao 批量识图评分、
`100.0% accuracy`、`GRADE PASSED`，全程未调用提交逻辑。

## 验证基线
- 后端单元测试：588 passed（新增 0/0 扫描与已完成剔除用例）。
- 前端类型检查：通过。
