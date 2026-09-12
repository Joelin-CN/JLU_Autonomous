# 后端自动化体系 — 架构全景（多平台）

> **版本**: 2.0　**最近更新**: 2026-09-12（同步智慧树 M0–M3 / core+platforms 平台架构落地）
> 上一版: 2026-06-24（v17+ 单平台全景，见 [archive/](../changelog/archive/) 或 git 历史）

> ⚠️ **历史提示**：DeepSeek 双引擎已移除（AI 仅 Doubao API）；`chaoxing/` 包现为兼容垫片
> （见 §二），实际实现位于 `core/` 与 `platforms/<platform>/`。最新契约见 [api.md](api.md)
> 与 [integration.md](integration.md)。

---

## 一、多平台架构总览（M1 落地，2026-09）

```
Electron 主进程 (job:start, StartJobPayload.platform)
        │  spawn python -m platforms.<platform>.api   (缺省 chaoxing)
        ▼
┌─────────────────────────────────────────────────────────────┐
│  core/  （平台无关层：协议 / 引擎 / 内存 / 追踪 / AI / 工具）    │
│  orchestrator.py  多账号并发 · 内存门 · 泳道结果（ModuleRunner  │
│                   惰性 getattr —— 平台模块按名解析）            │
│  browser/  playwright-cli 封装（会话 {platform}-chrome-{N}）   │
│  credentials.py  通用凭据解析（{...} 分块多账号格式）           │
│  memory.py · tracking/ · ai/ · engine 协议层                  │
└──────────────┬──────────────────────────────┬────────────────┘
               ▼                              ▼
   ┌──────────────────────┐        ┌──────────────────────────┐
   │ platforms/chaoxing/  │        │ platforms/zhihuishu/     │
   │ auth（密码登录+验证码）│        │ auth（扫码优先+密码/滑块   │
   │ scanner · solvers/    │        │  兜底 + storageState 会话）│
   │ （quiz / content bot）│        │ scanner（课程+章节树）     │
   │ captcha · font        │        │ video（D6 原速播放）       │
   └──────────┬───────────┘        │ accounts · courses 子命令 │
              │                     └──────────┬───────────────┘
              │                                │
              ▼                                ▼
   凭据 data/passwords/chaoxing.txt   凭据 data/passwords/zhihuishu.txt
   档案 chrome-profiles/chaoxing-*/   档案 chrome-profiles/zhihuishu/account-N/
                                      （含 storage-state.json 免扫码）

   ┌───────────────────────────────────────────────────────────┐
   │ chaoxing/（兼容垫片）: sys.modules 别名表 + 5 个 -m 入口自替换 │
   │ 转发 → 旧命令 python -m chaoxing.api 与 monkeypatch 语义不变 │
   └───────────────────────────────────────────────────────────┘
```

- **NDJSON 事件协议平台无关**（8 事件类型不变，见 api.md §4.3）——平台差异只出现在
  业务 payload（如智慧树扫码工单自带 `imageBase64` + `timeoutSeconds`）。
- **环境变量**：`CHAOXING_*` 全平台语义保留；智慧树专属 `ZHIHUISHU_ACCOUNTS_FILE` /
  `ZHIHUISHU_HEADED`（见 api.md §4.1 白名单表）。
- **平台能力现状**：超星全套（扫描/内容/答题）；智慧树 M2（登录+扫描）+ M3（视频）已落地，
  M4（答题）与滑块自动求解未做（见 [../roadmap/zhihuishu.md](../roadmap/zhihuishu.md)）。

## 二、后端目录与核心模块

```text
backend/
├── core/               # 平台无关层（M1 从 chaoxing/ 上收）
│   ├── orchestrator.py #   多账号编排 · ModuleRunner 惰性平台解析
│   ├── credentials.py  #   通用 {...} 分块凭据解析
│   ├── memory.py       #   预算公式 · CIM 采样 · MemoryMonitor
│   ├── browser/        #   playwright-cli 封装 + orphans 孤儿清理
│   ├── engine/         #   NDJSON 协议层（stdin 控制信号解析）
│   └── ai/ · tracking/ · font/ · utils
├── platforms/
│   ├── chaoxing/       # 超星实现（auth/scanner/solvers/captcha/…，即原 chaoxing/ 包内容）
│   └── zhihuishu/      # 智慧树实现（api/auth/scanner/video/accounts/courses）
├── chaoxing/           # 兼容垫片（sys.modules 别名 + -m 入口转发，仅保旧入口可用）
└── tests/              # unit / integration / e2e（618+ 用例，平台包各自覆盖）
```

| 模块 | 角色 | 说明 |
|------|------|------|
| `core/orchestrator.py` | **顶层调度** | `run_for_account()` → 平台模块按名解析（ModuleRunner），多账号并发/内存门/泳道结果 |
| `platforms/chaoxing/solvers/` | **超星内容/刷题 bot** | `ChapterContentBot` / `ChapterQuizSolver`（v17 inline chaining；流程见 §三/§四） |
| `platforms/zhihuishu/video.py` | **智慧树视频处理器** | D6 原速策略（§二.1） |
| `platforms/*/auth.py` | **登录** | 超星：密码+验证码；智慧树：扫码优先（§二.1） |
| `core/browser/` | **浏览器引擎** | playwright-cli 封装；会话 `{platform}-chrome-{N}`；`orphans.py` 通用孤儿清理 |
| `core/ai/` | **AI 后端** | 仅 Doubao API（OpenAI SDK，文本+多模态识图）——DeepSeek 已移除 |

### 二.1 智慧树链路要点（M2/M3 实测结论）

- **登录（auth.py）**：扫码优先——扫码登录页二维码截图走 TICKET 工单（`imageBase64` +
  `timeoutSeconds`，用户 App 扫码后自动继续）；密码登录兜底（必触发易盾滑块，自动化环境
  被指纹检测拒绝，仅人工拖拽可行——D2 调研实证）；**storageState 会话**：登录成功导出
  `chrome-profiles/zhihuishu/account-N/storage-state.json`，下轮任务注入 Cookie 实测**零扫码**
  （75 cookies 恢复直接登录，扫描 34s vs 首轮扫码 105s）。
- **视频（video.py，D6 决策）**：**仅 1.0 倍速真实播放**——不碰倍速菜单；播放/静音/下一节
  全走站点控件真实点击；观察 JS 只读（`paused`/`currentTime`）；4–7s 人味轮询；**禁心跳伪造**。
  实测 0.1 节 456/456s 原速完整播放，全程无人值守。
- **三种弹窗自动化**：学前必读（右上角 X 带重试）、课程提醒（「下次再说」每轮清扫）、
  **弹题（试选 → `.answer` 揭示正确项 → 改选，纯 DOM 处理，不依赖 AI）**。
- **锁课红线**：异常学习行为会**锁课**（M0 调研实测触发）——锁课检测 → 跳过 + 申诉链接工单；
  工程红线已固化（禁倍速/禁伪造，见 roadmap ADR D6）。
- **章节树**：el-scrollbar 懒加载，需滚动加载全量节点（~38 节点实测）。


### JS 注入文件（位于 `platforms/chaoxing/js/`，`scripts/` 保留副本）

| 文件 | 注入方式 | 角色 |
|------|----------|------|
| `_v17_section_player.js` | `pw_run_code_file()` | **视频顺序播放 (主)** — v17 内联链式自动下一节，避免同时播放触反爬 |
| `_v11_phase2_fallback.js` | (保留, 未主动使用) | 视频顺序播放 (旧版) |
| `_v10_js_combined.js` | (保留, 未主动使用) | 视频播放控制 (更旧版) |
| `_decrypt_font.js` | `ensure_font_decrypt_loaded()` | **字体解密引擎** — MD5 + Typr.js + `_cxDecryptFont()` |
| `_resize_vp.js` | `ensure_chaoxing_viewport()` | **视口缩放** — 2048×1152 保证截图质量 |
| `_debug_innertext.js` | (调试用) | 调试 innerText 提取 |

### 配置文件

| 文件 | 内容 |
|------|------|
| `backend/chaoxing_config.json` | 共享配置 — 课程、AI provider 选择 (doubao-api / deepseek-web)、session 名称、超时/重试参数 |
| `chaoxing/data/_table.json` | 字体映射表（cxsecret 解密 key, 355KB） |

---

## 三、Content Bot 处理流程（视频，`platforms/chaoxing/`）

```
ChapterContentBot.run(start_chapter, start_section)
│
├─ open_course_chapters()
│   └─ pw_goto_course(courseid, clazzid, cpi)
│       → https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu?...
│
├─ check_progress() → "N/M" 从快照解析
│
├─ for each chapter.section (inline chaining 优化):
│   │
│   ├─ [每 3 节] _check_anti_spider()        ← 反爬预检
│   │   ├─ Check 1: URL 是否 antispider*.ac？ → 拦截
│   │   ├─ Check 2: iframe 内是否含验证码文字？ → 拦截
│   │   ├─ DOM fetch 验证码图片 (fetch img.src → base64 → PNG)
│   │   ├─ DeepSeek / Doubao 识图识别 → 正则提取 3-6 位码
│   │   ├─ 自动填充 → 提交
│   │   └─ 失败 → 手动等待 (10分钟超时)
│   │
│   ├─ complete_section(chapter_num, section_num, task_count)
│   │   │
│   │   ├─ navigate_to_section()
│   │   │   └─ 点击章节链接 → 等待 studentstudy 页面加载
│   │   │
│   │   ├─ _detect_content_type() → video / document / audio / ?
│   │   │
│   │   ├─ _handle_video()
│   │   │   ├─ _check_anti_spider()          ← CAPTCHA 预检
│   │   │   └─ _play_videos()
│   │   │       ├─ ensure_font_decrypt_loaded()  (预加载字体解密, 防反爬)
│   │   │       └─ pw_run_code_file(_v17_section_player.js)
│   │   │           │
│   │   │           ├─ Step 1: 读 JC.attachments → 视频列表
│   │   │           ├─ Step 2: Pre-check 已完成视频 (innerHTML 检测)
│   │   │           ├─ Step 3: Sequential 逐个播放
│   │   │           │   ├─ v[i]: click play → wait dur+60s (poll 每 5s)
│   │   │           │   ├─ 每 30s 检测 CAPTCHA (body text 关键字)
│   │   │           │   └─ timeout → 下一个
│   │   │           ├─ Step 4: all-complete → 返回 "advanced" (v17 内联链式)
│   │   │           └─ v17 自动点击 "下一节" → 无需回到章节树
│   │   │
│   │   ├─ _handle_document()     ← PDF/文档翻页
│   │   ├─ _handle_audio()        ← 音频播放
│   │   └─ _try_force_complete()  ← 强制标记完成 (备用)
│   │
│   ├─ result="advanced" → inline_chain=True  (v17自动到了下一节)
│   ├─ result="completed"/"skipped" → go_back_to_chapter_tree()
│   │   └─ 失败 → open_course_chapters() (整页刷新回退)
│   └─ result="failed" → go_back + 记录错误
│
└─ Summary (completed / skipped / failed)
```

---

## 四、Quiz Solver 答题流程（`platforms/chaoxing/`）

```
ChapterQuizSolver.run()  (正常模式 / grade_only 模式)
│
├─ open_course() → 导航到课程 + 点击 章节 tab
│
├─ for remaining_quiz_sections:
│   └─ solve_quiz(section, retry_depth=0)
│       │
│       ├─ [dry-run] 跳过所有实际操作
│       │
│       ├─ 1. navigate_to_section() → 进入章节测试页
│       │
│       ├─ 2. 等待 quiz iframe 加载
│       │
│       ├─ 3. 【策略 1：优先】字体解密 → 文本模式 (Tab0)
│       │   └─ get_decrypted_quiz_text()
│       │       ├─ ensure_font_decrypt_loaded() → 注入 _decrypt_font.js
│       │       ├─ decrypt_font_cxsecret() → 调用 window._cxDecryptFont()
│       │       └─ ai_solve_quiz() → AI 文本解答 (Doubao API / DeepSeek Web)
│       │
│       ├─ 4. 【策略 2：主截图方案】V2 .TiMu 容器截图 → 批量识图
│       │   └─ _capture_question_screenshots_v2()
│       │       ├─ 遍历 iframe 中所有 .TiMu 容器
│       │       ├─ element.screenshot() 逐题截图 (高精度)
│       │       ├─ 同时提取: img count, text preview, qid, qtype
│       │       └─ _solve_batched() → 批量发送 AI 识图
│       │
│       ├─ 5. 【策略 3：回退】旧版逐题 clip 截图 → 识图模式
│       │   └─ _capture_question_screenshots()
│       │       └─ 每题独立 clip 截图 → 单 batch AI 识图
│       │
│       ├─ 6. 【策略 4：回退】全页截图 → 识图模式
│       │   └─ _capture_quiz_screenshot()
│       │
│       ├─ 7. 【策略 5：最后手段】快照文本 → 文本模式
│       │   └─ pw_snapshot() → extract_questions_from_snapshot()
│       │       └─ _clean_snapshot_for_deepseek() → AI 文本解答
│       │
│       └─ ┌─ [grade_only 模式] ─────────────────────┐
│           │ _fill_answers(answers)                   │
│           │ _capture_filled_screenshots_v2()         │
│           │ _grade_batched() → AI 批改              │
│           │ → accuracy / correct / incorrect          │
│           └────────────────────────────────────────┘
│           ┌─ [正常模式] ────────────────────────────┐
│           │ _fill_answers(answers)                   │
│           │   ├─ _click_option_dom() 容器隔离点击     │
│           │   └─ _fill_blank() 填空题填充             │
│           │ _submit_quiz()                           │
│           │   ├─ _submit_quiz_native() 原生提交       │
│           │   └─ snapshot 回退 + 确认弹窗处理          │
│           │ _parse_score(snapshot) → 解析得分         │
│           │ score < 100 → 查看答案 → 重试 (max 10)    │
│           └────────────────────────────────────────┘
│
└─ Summary + QuizStats 输出 (_quiz_stats_<course>.json)
```

---

## 五、CAPTCHA 处理链（`platforms/chaoxing/`；智慧树登录工单形态见 api.md §3.2）

```
触发点:
  ├─ Content Bot: _check_anti_spider()  ← 每3节 + 视频播放前
  ├─ Content Bot: _v11_phase2_fallback.js  ← 每30s检测
  ├─ Quiz Solver:  (暂无 — quiz 页较少触发)
  └─ 独立调用: _solve_captcha.py

处理流程:
┌─────────────────────────────────────────────────────────┐
│  1. 检测                                                 │
│     ├─ Check URL: antispiderShowVerify.ac → 拦截         │
│     ├─ Check iframe (antispider frame → mooc frame)      │
│     └─ 关键字: 操作异常 / 验证码 / 9010                   │
│                                                         │
│  2. 提取图片 (DOM fetch — 无损原图)                       │
│     ├─ targetFrame.evaluate(() => {                      │
│     │     img.src → fetch → blob → FileReader            │
│     │   })                                               │
│     └─ base64 decode → _captcha_img.png                  │
│                                                         │
│  3. AI 识别 (DeepSeek Tab1 / Doubao API 多模态)          │
│     ├─ DeepSeek: ask_deepseek_image()                    │
│     └─ Doubao: doubao_ask_image()                        │
│     ├─ upload captcha_img.png                            │
│     └─ prompt: "请识别图片中的验证码文字"                   │
│                                                         │
│  4. 答案提取 (v16 改进)                                    │
│     ├─ 噪音清洗: 移除 prompt echo + UI 文字               │
│     ├─ 正则 Strategy 1: [A-Za-z0-9]{4} (最常见)           │
│     ├─ 正则 Strategy 2: 空格容忍 → "W t H C" → "WtHC"     │
│     └─ 正则 Strategy 3: 任意3-6位字母数字                  │
│                                                         │
│  5. 自动填充                                              │
│     ├─ 定位: antispider iframe → mooc iframe → 主页       │
│     ├─ input[name="ucode"] / input[type="text"]           │
│     ├─ fill(answer) → click 提交按钮                      │
│     └─ 验证: URL 不再含 antispider → solved               │
│                                                         │
│  6. 回退: 手动等待 (10分钟)                                │
│     ├─ 每 5s 检测 CAPTCHA 是否消失                        │
│     ├─ 监听外部 _captcha_answer.txt                      │
│     └─ timeout → 标记失败                                 │
└─────────────────────────────────────────────────────────┘
```

---

## 六、AI 后端（`core/ai/`）

> DeepSeek Web 引擎已于 2026-08 移除，**AI 仅支持 Doubao API**（渲染层 `AIProvider` 类型
> 固化为 `'doubao'`，后端任意 provider 值归一化）。

### Doubao API — HTTP API

```
core/ai/（doubao）
│
├─ _read_doubao_credentials()
│   └─ 解析 data/passwords/doubao.txt → ARK_API_KEY + model
│       API endpoint: https://ark.cn-beijing.volces.com/api/v3
│
├─ doubao_solve_quiz(text, course, section, timeout=180)
│   └─ OpenAI SDK chat.completions.create → parse JSON
│       温度: 0.1, 重试: 指数退避 2s→4s→8s (max 3)
│
├─ doubao_solve_quiz_image(paths, course, section, timeout=180)
│   └─ 多模态: text prompt + N 张 base64 图片 → 单次 API 调用
│
└─ doubao_ask_image(paths, prompt, timeout=180)
    └─ 通用多模态查询 (CAPTCHA 识别, 批改)
```

### AI 路由 (utils.py)

```python
ai_solve_quiz()         → doubao (文本)
ai_solve_quiz_image()   → doubao (识图)
ai_grade_quiz_image()   → doubao (批改)
```

---

## 七、字体解密流程

```
┌─────────────────────────────────────────────────────┐
│  get_decrypted_quiz_text()                          │
│                                                     │
│  1. ensure_font_decrypt_loaded()                    │
│     ├─ 定位 quiz iframe                             │
│     ├─ 检查 window._cxDecryptFont 是否已注入        │
│     └─ 未注入 → 注入 _decrypt_font.js               │
│         ├─ 最小化 MD5 (blueimp-md5)                 │
│         ├─ Typr.js (字体解析引擎)                   │
│         ├─ Font class (字形映射)                    │
│         └─ window._cxDecryptFont(doc, tableJson)    │
│                                                     │
│  2. decrypt_font_cxsecret()                         │
│     ├─ 读 _table.json → 字体映射表                  │
│     ├─ 定位 quiz iframe (含 .font-cxsecret 元素)    │
│     └─ 调用 window._cxDecryptFont(doc, tableJsonStr)│
│         └─ 返回 {ok: true, decrypted: N}            │
│                                                     │
│  3. 提取解密后文本 → DeepSeek 文本模式答题           │
└─────────────────────────────────────────────────────┘
```

---

## 八、工具层函数速查 (utils.py)

| 分类 | 函数 | 用途 |
|------|------|------|
| **Playwright CLI** | `pw(*args)` | 底层 playwright-cli 命令 |
| | `pw_snapshot()` | ARIA ref 树快照 |
| | `pw_click(ref)` | 点击 ARIA ref |
| | `pw_goto(url)` | 页面导航 (JS 注入绕过 Shell 转义) |
| | `pw_fill(ref, text)` | 填充输入框 (剪贴板) |
| | `pw_run_code(js)` | 执行 JS 代码 |
| | `pw_run_code_file(path)` | 执行 JS 文件 (shell=False) |
| | `pw_extract_result(output)` | 从 playwright-cli 输出提取返回值 |
| | `pw_goto_course(id, clazz, cpi)` | 打开课程 studentstudy |
| | `ensure_chaoxing_viewport()` | 视口 2048×1152 |
| **Session** | `set_active_session(name)` | 设置线程本地会话名 |
| | `_get_active_session()` | 获取当前会话名 |
| **快照解析** | `parse_progress_from_snapshot()` | (已完成, 总数) |
| | `find_ref_by_text(snap, text)` | 按文本找 ARIA ref |
| | `find_refs_by_pattern(snap, pat)` | 正则匹配 ref |
| **AI 路由** | `ai_solve_quiz(qs, course, sec)` | 文本模式 → 按 provider 分发 |
| | `ai_solve_quiz_image(ps, course, sec)` | 图片模式 → 按 provider 分发 |
| | `ai_grade_quiz_image(ps, prompt)` | 批改 → 按 provider 分发 |
| **字体** | `ensure_font_decrypt_loaded()` | 注入解密 JS |
| | `decrypt_font_cxsecret()` | 执行解密 |
| | `get_decrypted_quiz_text()` | 一键解密+提取文本 |
| **登录** | `chaoxing_login(idx)` | 自动登录 (JS DOM 填表) |
| | `is_chaoxing_browser_open()` | 检查会话是否存在 |
| | `ensure_chaoxing_browser(idx)` | 打开浏览器+设置窗口标题 |
| **扫描** | `scan_courses()` | 扫描未完成课程列表 |
| | `scan_course_sections(id, clazz, cpi)` | 扫描章节树 |
| **凭证** | `read_all_chaoxing_credentials()` | 解析多账号 |
| | `read_chaoxing_credentials()` | 向后兼容单账号 |
| **进度** | `ProgressTracker` | JSON 持久化 (completed_courses, sections_done, errors) |
| **控制** | `check_pause()` | 检测 `.pause_flag` / `.quit_flag` |
| **日志** | `log(msg, level)` | 时间戳 + 线程名 + flush |
| | `progress(idx, step, cur, total)` | PROGRESS 行输出 |
| **配置** | `load_config()` / `cfg(key)` | 读 chaoxing_config.json |

---

## 九、视频顺序播放 JS 协议

**当前使用**: `_v17_section_player.js` (主) — v17 支持内联链式自动下一节，完成后无需回到章节树。
**保留文件**: `_v11_phase2_fallback.js`, `_v10_js_combined.js` (旧版, 未主动使用)

`_v17_section_player.js` 返回的字符串格式（兼容旧协议）:

```
<result-type>:<detail> t=<elapsed> seqIdx=<N> vid=<N> || [<debug-array>]
```

| result-type | 含义 |
|-------------|------|
| `all-complete` | 全部视频完成 |
| `captcha-detected` | 播放中检测到验证码 |
| `no-kc-frame` | 找不到 knowledge card iframe |
| `no-video-frames` | 找不到视频 iframe |

Debug array 示例：
```
[
  "VID tasks=4 vfs=4 atts=4",
  "VID pre-check: done=0 notDone=4",
  "VID play[0] 振动（一） dur=1476s",
  "VID wait[0]=1537s cycles=308",
  "VID seq-timeout[0] after 1537s",
  "VID seq-start[1] 振动（二）",
  "VID click-err[1]: locator.count: Frame was detached"
]
```

---

## 十、配置（chaoxing_config.json）

`backend/chaoxing_config.json` 为共享配置（课程过滤、超时/重试参数、session 名称；示例见
`chaoxing_config.example.json`）。AI Provider 固定 `doubao-api`。**个人课程进度等运行时数据
不入库、不写入文档**（凭据与数据红线见 [../standards/secrets.md](../standards/secrets.md)）。

---

## 十一、运行命令速查

> ⚠️ 多平台布局（M1）后：任务主入口为 `python -m platforms.<platform>.api`（Electron 按
> `StartJobPayload.platform` spawn，缺省 chaoxing）。以下 `python -m chaoxing.*` 旧命令经
> `chaoxing/` 兼容垫片自替换转发，语义完全不变；`scripts/*.py` 为更早的向后兼容 shim。

```bash
# === 推荐方式：通过 Python 包入口 ===
python -m chaoxing.orchestrator --dry-run
python -m chaoxing.orchestrator --course "概率论与数理统计"
python -m chaoxing.orchestrator --quiz-only --course "概率论与数理统计"
python -m chaoxing.orchestrator --content-only --course "大学物理ABC（下）"
python -m chaoxing.orchestrator --scan-only
python -m chaoxing.orchestrator --status
python -m chaoxing.orchestrator --resume

# 多账户并行
python -m chaoxing.orchestrator --all-accounts --dry-run
python -m chaoxing.orchestrator --accounts "0,2"
python -m chaoxing.orchestrator --all-accounts --yes  # 跳过确认

# === 向后兼容：通过 scripts/ shim ===
python scripts/chaoxing_orchestrator.py --dry-run
python scripts/chaoxing_orchestrator.py --course "概率论与数理统计"
python scripts/chapter_content_bot.py --course "大学物理ABC（下）" --start-chapter 4
python scripts/chapter_quiz_solver.py --course "概率论与数理统计" --dry-run
python scripts/chapter_quiz_solver.py --course "概率论与数理统计" --section "2.7" --grade-only

# CAPTCHA 独立解决
python scripts/_solve_captcha.py

# 通过 CLI 入口 (推荐)
chaoxing_cli.bat status
chaoxing_cli.bat scan
chaoxing_cli.bat full-auto --course "概率论与数理统计"
chaoxing_cli.bat batch-test --from 2.7
chaoxing_cli.bat full-auto --all-accounts --headed
```

---

## 内存感知并发（2026-08-13）

- **Electron 主进程**：`electron/memory/planner.ts` 在每次 `JOB_START` 前取样基线
  （扣除遗留项目 Chrome 占用），计算内存预算与 CPU 保险值，把
  `--max-concurrent/--budget-gb/--system-limit-gb/--per-account-estimate-gb`
  传给 Python；运行时只消费后端 `MEMORY` 事件驱动仪表。
- **Python 后端**：`core/memory.py` 提供预算公式、PowerShell CIM 采样与
  `MemoryMonitor`（M1 已上收至 core，平台无关）；`core/orchestrator.run_multi_account`
  用运行时信号量排队，每个账号在打开 Chrome 前执行 `gate_open()` 预算闸门，超预算等待、
  绝不瞬时突破。
- **凭据**：AI key 由主进程原子写 `data/passwords/doubao.txt`（`.bak` 备份、
  写后读回校验，只回显尾号）；账号增删改由 `platforms.<platform>.accounts` 子命令原子写
  当前生效账号文件（`CHAOXING_ACCOUNTS_FILE` 可覆盖路径），显式编号防止档案错位。
- **任务运行中**锁定所有写操作（AI 配置、账号、账号路径），由主进程 `jobState`
  统一把关。
