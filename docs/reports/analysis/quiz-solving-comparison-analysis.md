# 做题逻辑与工作流差异分析

> 分析日期：2026-06-23 | 更新: 2026-06-24  
> 对比对象：我的脚本 vs etc/ 中三个参考脚本  
> **更新 (06-24)**: 我的脚本现已支持双 AI 后端 — Doubao API (HTTP, 默认) + DeepSeek Web (浏览器自动化)。V2 截图策略 (.TiMu 容器 element.screenshot()) 为当前主方案。

---

## 概览

| 脚本 | 类型 | 作者 | 答案来源 |
|---|---|---|---|
| **我的脚本** | Python + Playwright CLI 外挂 | — | DeepSeek AI（文字 + 识图） |
| 参考脚本1 (referrence_scripts.txt) | Tampermonkey 页内注入 | isMobile / noshuang | 第三方题库 API（tikuhai.com） |
| 参考脚本2 (referrence_scripts2.txt) | Tampermonkey 页内注入 | — | DeepSeek AI 代理（api.116611.xyz） |
| 参考脚本3 (referrence_scripts3.txt) | Tampermonkey 页内注入 | 爱吃蛋炒饭 | 双层题库（免费 + 付费）+ 众包回传 |

---

## 1. 答案来源策略

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **答案来源** | DeepSeek AI（文字 + 识图） | 第三方题库 API | DeepSeek AI 代理 | 免费题库 + 付费题库双层 |
| **题库/API** | 无题库，纯 AI 推理 | `api.tikuhai.com/search` | `api.116611.xyz/v1/chat/completions` | `cx.icodef.com`（免费）→ `api.tikuhai.com`（付费） |
| **识图能力** | ✅ DeepSeek 识图模式 | ❌ | ❌ | ❌ |
| **费用** | 免费（自备 DeepSeek） | 需要密钥 token | 付费授权 + 免费试用 10 次 | token 付费（tikuhai） |
| **答案反馈闭环** | 无 | 无 | 无 | ✅ 众包回传正确答案到题库 |

### 解读

- **我的脚本**：双 AI 后端 — Doubao API (HTTP, 默认, 支持多模态) + DeepSeek Web (浏览器自动化, 识图)。纯 AI 推理，灵活性最高，能处理图片题和公式题。Doubao API 速度快，DeepSeek Web 慢但识图能力强。
- **参考脚本1/3**：依赖题库，覆盖面有限但速度快（毫秒级响应）。
- **参考脚本2**：也是纯 AI，但走付费代理，多了授权验证层。
- **参考脚本3 独有**：`getScore()` 系列函数解析结果页正确答案后回传到 tikuhai 题库，形成「做题→纠错→入库」闭环。

---

## 2. 题目检测与解析

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **解析方式** | 字体解密 → 正文提取 / 截图 → AI 识图 / 快照文本清洗 | DOM 选择器解析（`.TiMu` / `.questionLi`） | 11 种选择器遍历 + 全文降级搜索 | jQuery 选择器（`.fontLabel` / `.mark_name` / `.answer_p`） |
| **题型推断** | 依赖 AI 从文本/图片中判断 | 启发式 DOM 结构推断（checkbox/radio/textarea/选项数） | 中文标签匹配（单选题→single 等） | hidden input `answertype` 值直接读取（0=单选, 1=多选, 2=填空, 3=判断, 4=简答...） |
| **选项提取** | AI 从截图/文本中识别 | DOM 精确提取 `.answerBg` / `.fl.after` | `.stem_answer > div` 等多层选择器 | `.after` / `.answer_p` |
| **图片题/公式题** | ✅ 截图直接发给 DeepSeek 识图 | ❌ HTML 清洗后丢失 | ❌ HTML 清洗后丢失 | ❌ HTML 清洗后丢失 |

### 解读

- **我的脚本**最大的优势：不依赖 DOM 结构。截图模式和字体解密模式对页面改版天然鲁棒。
- **三个参考脚本都强依赖 DOM 选择器**——超星改个 CSS 类名就会失效。
- **参考脚本3 题型检测最精准**：直接从 `<input name="answertype" value="0">` 读取，无需推断。我的脚本做字体解密后也可以读取这些 hidden input 辅助 AI。

---

## 3. 答案填写机制

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **填写方式** | Playwright 快照 ref 点击 | DOM 元素 `click()` | DOM 元素 click + dispatchEvent | jQuery click + aria 属性操作 |
| **选项匹配** | 文本精确匹配 + 选项字母（A/B/C/D） | **编辑距离相似度**（Levenshtein，阈值 85%） | 字母→nth-child 索引转换 | 精确匹配 → **模糊匹配降级**（阈值 80%）→ 随机选择 |
| **作用域隔离** | ✅ 每题取新快照 + 题目边界裁剪 | 每题独立元素内操作 | 每题独立 questionElement 内操作 | 每题独立 html 参数传入 |
| **UEditor 支持** | ❌（快照模式不需要） | ✅ `UE.getEditor().setContent()` | ✅ `UE.getEditor().setContent()` | ✅ `UE.getEditor().ready().setContent()` |
| **填空/简答** | 快照 textbox ref 填入 | UEditor API | UEditor API + textarea.value 降级 | UEditor API + clear 前置 |
| **判断正误** | AI 从文本推断 | 正则 true/false → aria-label 匹配 | 正则 true/false → nth-child | 正则 → `data='true'/'false'` 匹配 |
| **去重点击保护** | ❌ | ✅ 检查 `aria-checked === "true"` | ❌ | ✅ 检查 `aria-checked` + clear 前置 |

### 解读

- **我的脚本需要补充相似度匹配**：AI 返回的答案文本可能与选项文本不完全一致（如 AI 答 "对" 而选项是 "A. 正确"），精确匹配会失败。参考脚本1 的 Levenshtein 编辑距离匹配（阈值 85%）值得借鉴。
- **三个参考脚本都直接操作 DOM**，能利用 UEditor API 填写富文本答案。我的脚本走快照模式不需要这个。
- **参考脚本1/3 有去重点击保护**——检查 `aria-checked` 防止重复点击已选中选项。

---

## 4. 提交与验证

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **自动提交** | ✅ 查找"提交"/"交卷"按钮 + 确认弹窗 | ✅ 正确率 ≥ 85% 提交，否则暂存（`noSubmit()`） | ✅ 多层提交：btnBlueSubmit → submitWork → DOM查找 → 文本匹配 | ✅ 正确率 ≥ 80% 提交，否则 noSubmit |
| **分数解析** | Regex：`(\d+)\s*分` / `得分：(\d+)` / `(\d+)%` | ❌（依赖正确率计算） | ❌ | ✅ 详细 getScore 系列函数，回传正确答案 |
| **提交确认弹窗** | 查找"确定"/"确认"并点击 | `submitCheckTimes()` | `handleSubmitConfirmDialog()` 轮询弹窗 | `submitCheckTimes()` |
| **提交超时** | 无显式超时 | 无 | `waitForQuizSubmitCompletion(8000ms)` 轮询 | **200s 超时看门狗** |
| **Alert 拦截** | ❌ | ✅ `iframeWindow.alert = () => {}` | ✅ 替换 `window.alert` | ✅ 拦截 code-1 错误 |
| **提交参数校验** | ❌ | ❌ | ✅ `validateAndFixSubmitParams()` 补全 workRelationId/courseId/classId | ❌ |

### 解读

- **参考脚本2 的提交逻辑最完善**：多层降级（JS 函数 → DOM 选择器 → 文本匹配）+ 弹窗处理 + 完成轮询 + 参数校验。
- **参考脚本3 独有的分数解析后回传**——我的脚本重试时解析到的正确答案应该持久化保存，下次直接复用。
- **我的脚本需要补充 Alert 拦截**——提交后超星可能弹出 code-1 错误弹窗阻塞流程。

---

## 5. 重试 / 纠错策略

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **重试触发** | 分数 < 目标分（默认 100%） | 无内置重试 | 无内置重试 | 无内置重试 |
| **重试方式** | ① 查看答案→解析正确答案 ② 点击重试→填入正确答案 ③ 递归 AI 重解 | — | — | — |
| **重试上限** | 递归深度 5 + 最多 10 次循环 | — | — | — |
| **降级接受** | 深度耗尽时接受 ≥ 60% | 正确率不够就暂存（不提交） | — | 正确率不够就暂存（不提交） |

### 解读

- **我的脚本是唯一有完整重试策略的**，这是明显优势。三个参考脚本都是「一次搜索→填入→提交/暂存」的线性流程。
- "查看答案→解析→重试填入正确答案"这个循环是核心差异化能力。

---

## 6. 字体解密

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **解密库** | Typr.js + MD5（`_decrypt_font.js`） | Typr.js（内联在脚本中） | Typr.js + MD5（CDN 外链 `116611.xyz/typr-md5.js`） | Typr.js（内联 ~700 行） |
| **映射表** | `_table.json`（本地文件） | `@resource ttf`（forestpolice.org） | `@resource fontTableData`（116611.xyz） | `ttflist` 三个 CDN 降级加载 |
| **解密时机** | 做题前（作为第一优先路径） | `processWork()` 开头 | `tryEnterQuizAndAnswer()` 前注入 | `startChapter()` 开头 |
| **解密验证** | 检查解密后文本长度 > 50 字符 | 无显式验证 | 轮询 `.font-cxsecret` 数量归零 | 无显式验证 |

### 解读

- 实现原理完全相同：Typr 解析 TTF → MD5 glyph path → 查映射表 → 替换 `.font-cxsecret` 文字。
- 我的脚本映射表是本地文件，更可靠（不依赖外部 CDN），但可能过时。参考脚本从 CDN 加载可以热更新。
- 我的脚本把字体解密作为**第一优先路径**（最快最便宜），这是合理的设计选择。

---

## 7. 整体工作流架构

| 维度 | 我的脚本 | 参考脚本1 | 参考脚本2 | 参考脚本3 |
|---|---|---|---|---|
| **运行方式** | Python + Playwright CLI（外挂浏览器） | Tampermonkey 用户脚本（页内注入） | Tampermonkey 用户脚本（页内注入） | Tampermonkey 用户脚本（页内注入） |
| **触发方式** | 命令行主动执行 | **URL 自动匹配 + 页面监控** | 手动点击按钮 | **URL 自动匹配** |
| **流程编排** | 编排器 → QuizSolver → ContentBot（线性） | **RxJS 响应式**：URL 变化 → iframe 递归监控 → concatMap 管道 | **setInterval 轮询**（3s）+ 事件驱动（video ended） | **主动 API 调用**（gas/clazz → 遍历章节 → iframe 任务分派） |
| **课程发现** | ✅ `scan_courses()` + `scan_course_sections()` 动态扫描 | ❌ 被动等待用户进入页面 | ❌ 被动等待用户进入页面 | ✅ `api.getCourseChapter()` + `api.getChapterList()` |
| **多账号** | ✅ **多线程并行**（每账号独立浏览器会话） | ❌ 单页面 | ✅ 多 frame 所有权协议（localStorage heartbeat） | ❌ 单页面 |
| **断点续传** | ✅ `ProgressTracker` + `--resume` | ❌ | ✅ localStorage 持久化学习状态 | ❌ |
| **视频处理** | ✅ 独立 JS 播放器（顺序播放 + 自动下一节 v17 inline chaining） | ✅ 静音播放 + pause 监听重播 | ✅ 静音 + 倍速 + ended/timeupdate 监听 | ✅ **心跳上报**（MD5 加密进度）+ 视频内题目作答 |
| **闯关模式** | ❌ | ❌ | ❌ | ✅ 完整支持（`unlockChapter` API） |
| **复习模式** | ❌（只处理未完成章节） | ❌ | ❌ | ✅ 支持（重做已完成章节） |

### 解读

- **我的脚本是唯一能全自动「批量处理多账号」的**——外挂式架构天然支持。三个参考脚本都是页内注入，一个页面只能处理一个账号。
- **参考脚本3 功能最全**：闯关模式 + 复习模式 + 视频心跳上报。我的脚本缺少这些场景的支持。
- **我的脚本的视频 inline chaining（v17）** 是一个好的优化——减少回到章节树的往返，更像真人行为。

---

## 8. 四层做题降级策略（我的脚本独有）

```
优先级从高到低：

Tier 1: 字体解密文本模式 (fastest, cheapest)
  └─ get_decrypted_quiz_text()
      └─ 注入 _decrypt_font.js → 解密 .font-cxsecret → 读 body.innerText
      └─ 文本长度 > 50 字符 → 发给 AI 文字模式 (Doubao API / DeepSeek Tab0)

Tier 2: ⭐ V2 .TiMu 容器截图 + 批量识图 (primary, most accurate)
  └─ _capture_question_screenshots_v2()
      └─ 遍历 iframe 中所有 .TiMu 容器 → element.screenshot() 逐题截图
      └─ 同时提取 img count, text preview, qid, qtype 元数据
      └─ _solve_batched() → 批量发送 AI 识图 (Doubao API 多模态 / DeepSeek Tab1)

Tier 3: 旧版逐题 clip 截图降级 (legacy fallback)
  └─ _capture_question_screenshots()
      └─ 找 .newZy_TItle 题号元素 → 计算每题 Y 边界 → 逐题 clip 截图
      └─ single-batch AI 识图

Tier 4: 全页截图降级 (fallback for per-question)
  └─ _capture_quiz_screenshot()
      └─ 找 quiz iframe body boundingBox → 全页截图 → AI 识图

Tier 5: 快照文本 + AI 文字 (last resort)
  └─ extract_questions_from_snapshot()
      └─ pw_snapshot() → _clean_snapshot_for_deepseek()
      └─ 清洗 YAML 噪音 → AI 文字解答
```

这是三个参考脚本都**没有**的多层降级设计。V2 策略 (Tier 2) 是当前主方案，结合 Doubao API 多模态可实现快速批量解答。

---

## 9. 核心差异架构图

```
我的脚本（外挂式 Python — chaoxing/ 包）:
┌─────────────────────────────────────────────────┐
│  Python 编排器 (chaoxing/orchestrator.py)         │
│  ├─ Playwright CLI 控制浏览器（快照/DOM/截图）     │
│  ├─ 双 AI 后端: Doubao API (默认) + DeepSeek Web  │
│  ├─ 多线程并行多账号（Thread-local session）       │
│  ├─ 五层做题降级（文字→V2容器→逐题clip→全页→快照） │
│  ├─ Grade-Only 模式 (Phase C 批量验证)            │
│  └─ 本地 JSON 状态持久化 (断点续传)                │
│                                                  │
│  优势：跨页面、多账号、截图识图、断点续传、降级鲁棒   │
│        Doubao API 速度快, DeepSeek Web 识图强     │
│  劣势：需要 Python 环境、截图仍有一定耗时            │
└─────────────────────────────────────────────────┘

参考脚本1（页内注入 - noshuang / isMobile）:
┌─────────────────────────────────────────────────┐
│  Vue3 + Pinia + RxJS Shadow DOM 应用             │
│  ├─ URL 监控 → iframe 递归发现 → concatMap 管道   │
│  ├─ 题库 API tikuhai.com 查答案（5s 超时）         │
│  ├─ DOM 直接操作填入 + 相似度匹配                   │
│  ├─ 正确率 ≥ 85% 自动提交                          │
│  └─ 自动下一章                                    │
│                                                  │
│  优势：实时响应、题库快（毫秒级）、UI 完善           │
│  劣势：依赖题库覆盖面、无截图识图、单页面、依赖DOM   │
└─────────────────────────────────────────────────┘

参考脚本2（页内注入 - AI 回答）:
┌─────────────────────────────────────────────────┐
│  jQuery + 原生 JS                                │
│  ├─ 手动触发"开始答题"/"开始刷章节"                │
│  ├─ DeepSeek AI 代理（api.116611.xyz）            │
│  ├─ 正式测验专用解析（#form1 + answertype input）   │
│  ├─ 多层提交降级 + 弹窗处理 + 参数校验              │
│  └─ 多 frame 所有权协议                           │
│                                                  │
│  优势：AI 灵活、正式测验支持好、提交逻辑完善         │
│  劣势：付费、手动触发、无多账号                      │
└─────────────────────────────────────────────────┘

参考脚本3（页内注入 - 爱吃蛋炒饭）:
┌─────────────────────────────────────────────────┐
│  jQuery + layx UI                                │
│  ├─ URL 自动匹配 → 主动 API 拉取章节列表            │
│  ├─ 双层题库（免费→付费）+ 众包回传正确答案          │
│  ├─ 闯关模式 + 复习模式                           │
│  ├─ 视频心跳上报（MD5 加密进度）+ 视频内题目作答      │
│  └─ 200s 提交超时看门狗                           │
│                                                  │
│  优势：题库覆盖高、闯关模式、正确答案闭环、功能最全    │
│  劣势：部分付费、依赖 DOM 选择器、单页面               │
└─────────────────────────────────────────────────┘
```

---

## 10. 改进建议

| 优先级 | 借鉴来源 | 建议内容 |
|---|---|---|
| 🔴 高 | 参考脚本1 | **相似度匹配**：`_click_option()` 加入 Levenshtein 编辑距离模糊匹配，阈值 85% |
| 🔴 高 | 参考脚本1/3 | **正确率阈值提交**：设置 85%-90% 及格线，低于阈值调用 `noSubmit()` 暂存 |
| 🔴 高 | 参考脚本2 | **正式测验专用解析**：对 `/exam-ans/exam` 页面增加 `#form1` + `answertype` input 处理 |
| 🔴 高 | 参考脚本2 | **多层提交降级**：btnBlueSubmit → submitWork → DOM 选择器 → 文本匹配 |
| 🟡 中 | 参考脚本3 | **答案持久化**：重试时解析到的正确答案存入本地 JSON 题库，下次直接复用 |
| 🟡 中 | 参考脚本1/2 | **Alert 拦截**：提交后覆盖 `window.alert` 防止 code-1 弹窗阻塞 |
| 🟡 中 | 参考脚本3 | **闯关模式支持**：检测 `unlock` 状态并调用 unlock API |
| 🟢 低 | 参考脚本3 | **题型精确读取**：字体解密后从 `input[name^=answertype]` 读取题型辅助 AI 判断 |
| 🟢 低 | 参考脚本2 | **提交参数校验**：确保 `workRelationId`/`courseId`/`classId` 在 DOM 中存在 |
| 🟢 低 | 参考脚本3 | **映射表 CDN 更新**：`_table.json` 增加从 CDN 热更新的 fallback 路径 |
