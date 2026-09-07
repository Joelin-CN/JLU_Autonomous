# API 接口文档 — 超星学习通自动化

> **版本**: v2.0  
> **更新**: 2026-06-24  
> **目的**: 记录 Python ↔ JS ↔ CLI 三层接口，便于后续重构 bat/ps1 逻辑。  
> **变更**: v2.0 — 修正实际行数、添加 Doubao API 后端、V2 截图策略、Grade-Only 模式。

> ⚠️ **历史参考（2026-06）**：DeepSeek Web 后端已移除，`ai.provider` 仅支持 `doubao-api`；
> 主入口为 `python -m chaoxing.api`。最新三层契约见 [../api.md](../api.md)。

---

## 目录

1. [架构总览](#1-架构总览)
2. [CLI 层 (bat + ps1)](#2-cli-层-bat--ps1)
3. [Python Orchestrator 接口](#3-python-orchestrator-接口)
4. [utils.py — 核心工具库](#4-utilspy--核心工具库)
5. [chapter_quiz_solver.py — 答题引擎](#5-chapter_quiz_solverpy--答题引擎)
6. [chapter_content_bot.py — 内容机器人](#6-chapter_content_botpy--内容机器人)
7. [AI 后端接口](#7-ai-后端接口)
8. [JavaScript 注入接口](#8-javascript-注入接口)
9. [配置与状态文件格式](#9-配置与状态文件格式)
10. [CLI ↔ Python 通信协议](#10-cli--python-通信协议)

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────┐
│  chaoxing_cli.bat  ←→  chaoxing_cli.ps1              │  CLI 层
│  (最小启动器)           (交互菜单 + 命令路由 + KB监听)   │
├──────────────────────────────────────────────────────┤
│  chaoxing/orchestrator.py                            │  编排层
│  (多账户多线程调度 + 动态课程发现 + 进度管理)            │
├──────────────────────┬───────────────────────────────┤
│  chaoxing/solvers/   │  chaoxing/solvers/             │  执行层
│  quiz/ (答题引擎)     │  content/ (内容引擎)            │
│  + Grade-Only 模式    │  v17 inline chaining          │
├──────────────────────┴───────────────────────────────┤
│  chaoxing/browser/ + platform/ + font/ + utils/       │  基础层
│  (pw封装 / 登录 / 扫描 / 字体解密 / 快照解析)          │
├──────────────────────┬───────────────────────────────┤
│  chaoxing/ai/        │  chaoxing/ai/                  │  AI 层
│  deepseek.py         │  doubao.py (默认)               │
│  (浏览器自动化, 识图)  │  (HTTP API / OpenAI SDK)       │
├──────────────────────┴───────────────────────────────┤
│  playwright-cli  (浏览器自动化引擎)                     │  引擎层
│  Google Chrome    (持久化会话, 多Session隔离)           │
└──────────────────────────────────────────────────────┘
```

**AI 后端**: 双引擎 — `chaoxing/ai/doubao.py` (默认, HTTP API, 支持多模态) + `chaoxing/ai/deepseek.py` (浏览器自动化, 双Tab识图)。Provider 由 `chaoxing_config.json` 中 `ai.provider` 决定。

**数据流方向**: CLI → Python → playwright-cli → Chrome DOM / AI API → 返回结果

---

## 2. CLI 层 (bat + ps1)

### 2.1 chaoxing_cli.bat

**职责**: 最小启动器 — 绕过 PowerShell 执行策略 + UTF-8 编码

```batch
@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "chaoxing_cli.ps1" %*
```

**参数透传**: 所有 `%*` 直接传递给 `chaoxing_cli.ps1`。

**交互循环**: 命令执行完后询问 `Run another command? [y/N]`，输入 Y 重新进入菜单。

### 2.2 chaoxing_cli.ps1

**职责**: 统一入口点 — 交互菜单 + 命令路由 + 键盘监视器 + 结果汇总

#### 参数 (命令行模式)

| 参数 | 类型 | 说明 |
|------|------|------|
| `Command` | `string` (Position 0) | 命令名: `status` / `scan` / `solve-quiz` / `complete-content` / `full-auto` / `batch-test` |
| `-Course` | `string` | 目标课程名（子串匹配） |
| `-Section` | `string` | 目标章节号（如 `2.7`） |
| `-From` | `string` | batch-test 起始章节 |
| `-Account` | `int` | 账号索引 (0-based)，默认 0 |
| `-AllAccounts` | `switch` | 处理所有账号（多线程并行） |
| `-Headed` | `switch` | 显示浏览器窗口 |
| `-DryRun` | `switch` | 预览模式，不提交 |
| `-Resume` | `switch` | 从上次进度恢复 |
| `-ScanOnly` | `switch` | 仅扫描 |

#### 交互菜单流程

```
显示菜单 → [1-6/K/Q] 选择命令
→ 账号范围 (A/0,2/Enter)
→ 浏览器可见 (y/N)
→ 课程筛选（已移除，自动处理所有未完成课程）
→ [batch-test] 起始章节
→ [破坏性命令] Dry run? / Resume?
→ 确认页面
→ 执行
```

#### 键盘监视器 (Keyboard Monitor)

独立 PowerShell Runspace 运行的键盘监听线程：

```
按键 P → toggle .pause_flag 文件 → Python 侧 check_pause() 检测
按键 Q → 创建 .quit_flag 文件 → Python 侧抛出 KeyboardInterrupt
```

**通信机制**: 文件标志位 (`%ROOT%/.pause_flag`, `%ROOT%/.quit_flag`)

#### 环境变量 (传递给 Python 子进程)

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `CHAOXING_HEADED` | `"1"` / `"0"` | 浏览器可见模式 |
| `CHAOXING_WORKSPACE` | 项目根路径 | Python 侧路径解析 |
| `PYTHONIOENCODING` | `"utf-8"` | 强制 UTF-8 输出 |
| `PYTHONUTF8` | `"1"` | Python UTF-8 模式 |

#### 进度输出解析 (PROGRESS 行)

PS1 解析 Python stdout 中的 `PROGRESS:[N] current/total message` 行来渲染进度条。

```
格式: PROGRESS:[<account_index>] <current>/<total> <message>
示例: PROGRESS:[0] 3/5 Processing: 概率论与数理统计
      PROGRESS:[0] -/- Logging in...
      PROGRESS:[0] 5/5 DONE — 5 courses
```

#### Invoke-PythonScript (核心进程启动)

```
输入: ScriptName, Arguments, -Progress switch
处理:
  1. 定位脚本 (scripts/ → tests/)
  2. 创建 ProcessStartInfo (UseShellExecute=false, RedirectStdout/Stderr)
  3. 注册 OutputDataReceived / ErrorDataReceived 事件
  4. Progress 模式: 过滤非 PROGRESS: 行，渲染进度条
  5. Normal 模式: 逐行打印全部输出
  6. 3分钟超时检测 (无 PROGRESS 输出则警告)
  7. Quit 信号: 先 WaitForExit(30s) → 超时则 Kill()
```

#### Invoke-BatchTest (Phase C 批量测试)

```
流程:
  1. 确定账号列表 (AllAccounts / AccountList / Account)
  2. 固定 Quiz 顺序: [2.7, 1.6, 3.7, 3.8, 4.5, 4.6, 5.3, 5.4, 6.4, 6.5, 7.5, 7.6, 8.5, 8.6]
  3. 多账户: PowerShell Runspaces 并行
     每个 Runspace 运行 Invoke-BatchTestSingleAccount
  4. 单账户: 直接调用 Invoke-BatchTestSingleAccount
  5. 汇总所有账户结果
```

#### Invoke-BatchTestSingleAccount (单账户批量)

```
流程:
  1. 登录 (内联 Python 脚本) → 解析 LOGIN_OK:True/False
  2. 从 course listing JS 提取 courseid/clazzid/cpi
  3. 对每个 section:
     a. 导航 (_batch_nav.py) → 解析 NAV_OK:True/False
     b. 运行 _test_phase_c.py --skip-navigation
     c. 解析 PASSED! 和 Accuracy: XX%
  4. 连续 2 次失败 → 停止当前账户
```

---

## 3. Python Orchestrator 接口

### chaoxing_orchestrator.py

**入口函数**: `main()` → argparse 解析 → 路由

#### 命令行参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `--course` | `str` | 课程名筛选（子串匹配） |
| `--dry-run` | `flag` | 预览模式，不提交 |
| `--resume` | `flag` | 从上次进度恢复 |
| `--scan-only` | `flag` | 仅扫描课程/章节，不执行 bot |
| `--status` | `flag` | 输出每账户运行状态 + 聚合进度 |
| `--account N` | `int` | 单账户索引 (0-based) |
| `--accounts "0,2"` | `str` | 逗号分隔多账户 |
| `--all-accounts` | `flag` | 所有账户并行处理 |
| `--yes` | `flag` | 跳过确认提示 (headless 自动化) |
| `--quiz-only` | `flag` | 仅处理 quiz sections |
| `--content-only` | `flag` | 仅处理 content sections |

#### 核心函数

##### `cmd_status(args)` — 状态查询

```
输出: STATUS:[N] running=是/否 [progress=X/Y course_count=Z]

逻辑:
  1. 读取所有账号
  2. playwright-cli list 获取活跃会话
  3. 对每个活跃会话: scan_courses() 汇总进度
```

##### `run_for_account(account_index, creds, args)` — 单账户全流程

```
session_name = f"chaoxing-chrome-{account_index}"
set_active_session(session_name)

流程:
  Step 1: ensure_logged_in(account_index) → 登录/会话验证
  Step 2: discover_courses(args.course) → 动态发现课程+扫描章节
  Step 3: save_discovered_state() → 持久化用于 resume
  Step 4: 遍历 process_course(course, dry_run, quiz_only, content_only)
```

##### `discover_courses(course_filter)` — 课程发现

```
流程:
  1. scan_courses() → 获取未完成课程列表
  2. 过滤 (course_filter)
  3. 对每个课程: scan_course_sections() → 构建动态配置
  4. build_dynamic_course_config() → 组装标准格式
返回: list[course_config_dict]
```

##### `process_course(course, dry_run, quiz_only, content_only)` — 单课程处理

```
流程:
  Phase 1: ChapterQuizSolver(course).run()    [除非 content_only]
  Phase 2: ChapterContentBot(course).run()    [除非 quiz_only]
  验证最终进度 → 达100%则标记完成
```

##### `ensure_logged_in(account_index)` — 登录保障

```
逻辑:
  1. 检查浏览器会话状态
  2. 死会话检测: 空 snapshot → 关闭会话 → 重新登录
  3. "用户登录" 在 snapshot → 重新登录
  4. "个人空间" 在 snapshot → 已登录
```

##### 多线程模型

```
SHUTDOWN_FLAG = threading.Event()  (全局)

_run_account_in_thread() → 设置线程名 "chaoxing-account-N"
  → run_for_account() → 每账户独立 session

main() 中:
  threads = [Thread(target=_run_account_in_thread, args=(idx, cred, args)) ...]
  每个线程间隔约 0.5s（0.25–0.75s 随机抖动）启动
  join all with KeyboardInterrupt → SHUTDOWN_FLAG.set()
```

---

## 4. utils.py — 核心工具库

> **重构说明 (2026-06-24)**: `scripts/utils.py` 现在是向后兼容 shim，实际逻辑已拆分到 `chaoxing/` 子包：`chaoxing/config.py`、`chaoxing/browser/engine.py`、`chaoxing/platform/auth.py`、`chaoxing/font/`、`chaoxing/ai/router.py`、`chaoxing/tracking/` 等。

### 4.1 路径常量

```python
WORKSPACE   = Path(os.environ["CHAOXING_WORKSPACE"]) or Path(__file__).parent.parent
SCRIPT_DIR  = WORKSPACE / "scripts"          # 向后兼容 shim + 配置文件位置
PACKAGE_DIR = WORKSPACE / "chaoxing"          # 权威实现（Python 包）
CONFIG_PATH = SCRIPT_DIR / "chaoxing_config.json"   # 共享配置文件
OUTPUT_DIR  = WORKSPACE / "output"           # 持久化产物
TMP_DIR     = WORKSPACE / "temp"             # 临时文件
```

### 4.2 线程本地存储

```python
class _ThreadLocalStore:
    active_session: Optional[str]    # "chaoxing-chrome-N"
    font_decrypt_loaded: bool

set_active_session(name)  → 设置当前线程的会话名
_get_active_session()     → 线程本地 > 配置默认
```

### 4.3 Playwright CLI 封装

| 函数 | 签名 | 说明 |
|------|------|------|
| `pw(*args, timeout, use_shell)` | → `str` | 通用 playwright-cli 调用，自动附加 session |
| `pw_snapshot()` | → `str` | 带 boxes 的 YAML snapshot |
| `pw_click(ref)` | → `str` | 元素点击 |
| `pw_goto(url)` | | JSON 编码 URL → JS 注入导航 (绕过 & 符号 Shell 转义) |
| `pw_fill(ref, text)` | | 剪贴板粘贴填充 (避免文本回显) |
| `pw_run_code(js_code)` | → `str` | 内联 JS 执行 |
| `pw_run_code_file(filepath, timeout)` | → `str` | 文件 JS 执行 (shell=False 避免管道死锁) |
| `pw_extract_result(pw_output)` | → `str` | 从 `### Result` 节提取并 JSON 解码 |
| `pw_goto_course(courseid, clazzid, cpi)` | | 构造课程 URL 并导航 |

**Headed 模式**: 检查 `CHAOXING_HEADED` 环境变量，对 `open/click/fill/press/goto` 动作自动附加 `--headed`

**Shell 安全**: 
- `use_shell=True` (默认): 构建命令行字符串，Windows shell 安全引号
- `use_shell=False`: 列表形式参数 (避免长命令管道死锁)
- `pw_goto()`: 始终通过 JS 注入（JSON 编码 URL → 避免 `&` 被 cmd.exe 解释）

### 4.4 内部函数

| 函数 | 说明 |
|------|------|
| `_run_js_file(js_code, timeout)` | 写临时 JS → pw_run_code_file → 清理 → 返回 extracted result |

### 4.5 凭证管理

| 函数 | 返回 | 说明 |
|------|------|------|
| `read_all_chaoxing_credentials()` | `list[{account, password, website, index}]` | 解析 `data/passwords/chaoxing.txt` 多账号块 |
| `read_chaoxing_credentials()` | `(account, password, url)` | 向后兼容：返回第一个账号 |

**chaoxing.txt 格式**:
```
{
    website:"https://passport2.chaoxing.com/login?..."
    account[0]:手机号
    password[0]:密码
}
{
    website:"https://passport2.chaoxing.com/login?..."
    account[1]:手机号
    password[1]:密码
}
```

### 4.6 登录

| 函数 | 返回 | 说明 |
|------|------|------|
| `is_chaoxing_browser_open()` | `bool` | 会话是否存在 |
| `ensure_chaoxing_browser(account_index)` | `bool` | 打开浏览器 + 设置窗口标题 |
| `chaoxing_login(account_index)` | `bool` | **主登录**: JS DOM 操作填表 + 点击 |
| `_chaoxing_login_via_snapshot(account, password)` | `bool` | **回退登录**: snapshot ref + 剪贴板粘贴 |

**登录 JS 逻辑** (`chaoxing_login`):
```
1. 检查已登录 → 个人空间/i.chaoxing.com
2. 导航到登录页 (避免重复导航触发验证码)
3. JS 查找 input 元素 (placeholder 匹配 手机号/密码)
4. fill() 账号密码
5. 查找并点击 登录 按钮
6. 检测结果: still-on-login / captcha / logged-in
7. CAPTCHA 检测: 操作异常/滑块验证/请输入验证码/验证码已发送
```

### 4.7 课程扫描

| 函数 | 返回 | 说明 |
|------|------|------|
| `_ensure_on_course_listing()` | `bool` | 导航到个人空间 → 点击 课程 |
| `scan_courses()` | `list[{name, courseid, clazzid, cpi, done, total, percent, teacher}]` | 扫描课程卡片 |
| `scan_course_sections(courseid, clazzid, cpi)` | `{ok, course_name, done, total, quiz_sections, content_sections, chapters}` | 扫描章节树 |

**scan_courses JS 逻辑**:
```
1. 找 visit/interaction iframe
2. 滚动加载全部卡片
3. 遍历 div.course.learnCourse[id^="c_"]
4. 从 id="c_COURSEID" 和 info="CLAZZID_CPI" 提取 ID
5. innerText 解析: 课程名 / 任务点进度 / 百分比 / 教师 / 是否结束
6. 过滤: percent < 95% (近完成阈值) / 未结束 / total > 0
7. 按 courseid 去重
8. 按 progress 降序排列
```

**scan_course_sections JS 逻辑**:
```
1. 导航到课程页 → 点击 章节
2. 找 mooc2-ans studentcourse iframe
3. DOM 遍历 div.chapter_item:
   - .catalog_num em → 章节编号
   - .catalog_name a.clicktitle span → 章节名
   - id^="cur" → 小节项
   - .catalog_sbar → 小节号 (X.Y)
   - .catalog_state.icon_yiwanc → 已完成标记
   - 名称含 测试/测验/作业 → quiz 类型
4. 返回 chapters / quiz_sections / content_sections
```

### 4.8 字体解密

| 函数 | 返回 | 说明 |
|------|------|------|
| `ensure_font_decrypt_loaded()` | `bool` | 注入 `_decrypt_font.js` (Typr.js + MD5) |
| `decrypt_font_cxsecret()` | `{ok, decrypted}` | 在 quiz iframe 中执行解密 |
| `get_decrypted_quiz_text()` | `str` | 解密后取 innerText |

**注意**: 字体解密当前不完整，解密后仍有乱码，Tab0 文本模式默认禁用。

### 4.9 AI 路由

| 函数 | 说明 |
|------|------|
| `ai_solve_quiz(questions, course, section)` | DeepSeek Web 文本模式 |
| `ai_solve_quiz_image(image_paths, course, section)` | DeepSeek Web 识图模式 |
| `ai_solve_quiz_doubao(questions, course, section)` | Doubao API 文本模式 |
| `ai_solve_quiz_image_doubao(image_paths, course, section)` | Doubao API 多模态 |
| `ai_grade_quiz_image(image_paths, prompt, timeout)` | 批改路由 (按 provider 分发) |

### 4.10 进度追踪

```python
class ProgressTracker:
    state_file: Path   # output/progress_state[_session].json
    state: {completed_sections: [str], completed_courses: [str], errors: [dict]}
    
    mark_section_done(course_name, section)
    mark_course_done(course_name)
    is_section_done(course_name, section) → bool
    log_error(course, section, error)
    save()
```

### 4.11 日志

| 函数 | 说明 |
|------|------|
| `log(msg, level)` | 带时间戳+线程名输出到 stdout + `logs/chaoxing_YYYYMMDD.log` |
| `progress(account_index, step, current, total)` | 机器可读进度行 `PROGRESS:[N] current/total message` |

### 4.12 暂停/退出标志

```python
check_pause():
    if .quit_flag exists → unlink → raise KeyboardInterrupt
    while .pause_flag exists → sleep(0.5)
```

---

## 5. chapter_quiz_solver.py — 答题引擎

### 5.1 ChapterQuizSolver 类

```python
class ChapterQuizSolver:
    def __init__(self, course_config: dict, dry_run: bool = False,
                 grade_only: bool = False)
    # grade_only=True → Phase C: 仅填答案+截图+批改，不提交

    # ── 核心方法 ──
    def run()                          # 遍历 remaining_quiz_sections，调用 solve_quiz()
    def solve_quiz(section, retry_depth=0) → bool   # 主答题流水线 (多级降级)
    def open_course()                  # 导航到课程 + 点击 章节 tab
    def navigate_to_section(section_num) → bool   # 在章节树中点击小节链接
    def go_back_to_chapter_tree() → bool          # iframe 内返回章节树

    # ── AI 交互 ──
    def _get_ai_solver() → (text_fn, image_fn)     # 按 provider 配置选择 Doubao/DeepSeek
    def _solve_batched(q_infos, batch_size, section_key) → list[dict]  # 批量识图解答
    def _grade_batched(filled_infos, ai_answers, batch_size, section_key) → dict  # AI 批改

    # ── 截图 (V2 主方案 + 旧版回退) ──
    def _capture_question_screenshots_v2() → list[{index, path, qid, qtype, ...}]  # ⭐ 主方案
    def _capture_filled_screenshots_v2() → list[{index, path, qid, qtype, ...}]    # 填充后截图
    def _capture_question_screenshots() → list[str]                                 # 旧版 clip 回退
    def _capture_quiz_screenshot() → str | None                                     # 全页截图回退

    # ── 填充 ──
    def _fill_answers(answers) → int                          # 填充答案 (返回填充数)
    def _click_option(q_index, answer)                        # 点击选项 (文本模式)
    def _click_option_dom(q_index, answer_str, is_single_letter) → bool  # DOM容器隔离点击 (主)
    def _fill_blank(q_index, answer) → bool                   # 填空题专用

    # ── 提交 ──
    def _submit_quiz() → bool                                 # 提交 (native → snapshot 回退)
    def _submit_quiz_native() → bool                          # 原生表单提交
    def _parse_score(snap) → int | None                       # 解析分数
    def _parse_correct_answers(snap) → list[dict] | None      # 解析正确答案 (重试用)

    # ── 内部 ──
    def _detect_question_types() → list[{index, type}]        # DOM 检测题型 (radio/checkbox)
    def _clean_snapshot_for_deepseek(snap) → str              # 清理 YAML 噪声
```

### 5.2 solve_quiz 答题流水线

```
1. DRY RUN → 直接返回 True
2. 导航到小节 (仅首次)
3. 等待 quiz iframe 加载
4. Tab0 文本模式: font decrypt → 如果可用 (>50 chars 解密文本) → text AI
5. ⭐ V2 截图模式 (主): .TiMu element.screenshot() → _solve_batched() 批量 AI 识图
6. 旧版逐题 clip 截图回退: per-question clip → single-batch AI
7. 整页截图回退: 整个 iframe body 截图 → AI 识图
8. Snapshot 文本模式 (最后手段)
9. 填充答案 (_fill_answers / _click_option_dom / _fill_blank)
10a. [grade_only 模式] → _capture_filled_screenshots_v2 → _grade_batched (AI 批改)
10b. [正常模式] → _submit_quiz → _parse_score → 分数 < 目标 → 查看答案 → 重试 (max 10, 目标 100)
```

**Grade-Only 模式** (Phase C): `ChapterQuizSolver(course_config, grade_only=True)` — 仅截图+填答案+AI批改，不提交。用于批量验证 AI 答题准确率。阈值 `GRADE_PASS_THRESHOLD = 80%`。

### 5.3 V2 截图策略 (Strategy A)

```javascript
// 单次 JS pass: 找到所有 .TiMu 容器，逐个 element.screenshot()
for each iframe candidate:
  const timuEls = iframe.locator('.TiMu');
  for each .TiMu container:
    await el.scrollIntoViewIfNeeded();
    await el.screenshot({path});
    // 同时提取: img count, text preview, qid, qtype
```

### 5.4 DOM 容器隔离点击

```javascript
// Stage A: .TiMu / .questionLi 容器隔离
for each candidate iframe:
  const containers = iframe.locator('.TiMu');  // or '.questionLi'
  const container = containers.nth(q_index - 1);
  const optionEls = container.locator('[class*="before-after"]'); // TiMu
                 or container.locator('.answerBg');               // questionLi

// 已选择检测 (3级):
//   1. input#answer{qid}.value !== ''
//   2. aria-checked === 'true'
//   3. .check_answer / .check_answer_dx / input:checked

// 文本匹配 (规范化后):
//   单字母: 匹配首字母
//   全文: 规范化空格后精确/前缀/包含匹配

// Stage B (回退): .newZy_TItle Y坐标定位
```

### 5.5 QuizStats 统计

```python
class QuizStats:
    records: [{section, total_questions, ai_answers, score,
               correct_answers, retry_count, mode, per_question, ...}]
    
    record_attempt(section_key, total_questions, ai_answers, score, ...)
    summary() → {total_quizzes, avg_score, perfect_sections, per_question_accuracy, ...}
    
# 文件: output/_quiz_stats_<course_name>.json
```

### 5.6 Grade-Only 模式 (Phase C)

```
流程:
  1. 正常截图 + AI 解答
  2. 填充答案 (_fill_answers)
  3. 截图填充状态 (_capture_filled_screenshots_v2)
  4. 发送到 DeepSeek/Doubao 独立批改 (_grade_batched)
  5. 返回 accuracy / correct / incorrect / uncertain

阈值: GRADE_PASS_THRESHOLD = 80%
```

---

## 6. chapter_content_bot.py — 内容机器人

### 6.1 ChapterContentBot 类

```python
class ChapterContentBot:
    def __init__(self, course_config: dict, dry_run: bool)
    
    def run(start_chapter, start_section)                  # 主循环: 遍历章节
    def complete_section(chapter_num, section_num, task_count) → str  # 处理单个小节
    # 返回: "completed" | "skipped" | "advanced" | "failed"
    # "advanced" = v17 自动内联链式到了下一节
    
    def go_back_to_chapter_tree() → bool                   # iframe 内返回章节树
    def check_progress() → (done, total)                   # 快照解析进度
    def _check_anti_spider() → bool                        # 反爬检测 + 自动处理
    
    # 视频/音频/文档自动播放完成
    # 使用 _v17_section_player.js (主, 支持 inline chaining)
    # _v11_phase2_fallback.js / _v10_js_combined.js (保留, 未主动使用)
```

### 6.2 ContentBot 输入格式

```json
{
  "name": "概率论与数理统计",
  "courseid": "255106367",
  "clazzid": "127207872",
  "cpi": "415409200",
  "chapters": [
    {
      "num": 1,
      "name": "随机事件与概率",
      "sections": 7,
      "tasks_per": [2, 2, 2, 2, 2, 2, 0]
    }
  ]
}
```

### 6.3 内容完成策略

- **视频**: `_v17_section_player.js` 注入 → 定位 video 元素 → played/ended 检测 → seek 到接近末尾 → 自动点击 "下一节" (inline chaining, 无需回到章节树)
- **文档**: 滚动到底部 → 检测完成标记
- **音频**: 类似视频逻辑
- **JS 文件**: `chaoxing/js/_v17_section_player.js` (主 — 当前使用), `chaoxing/js/_v11_phase2_fallback.js` / `chaoxing/js/_v10_js_combined.js` (保留, 旧版)。`scripts/` 目录保留副本。

---

## 7. AI 后端接口

**配置选择**: `chaoxing_config.json` → `ai.provider`: `"doubao-api"` (默认) 或 `"deepseek-web"`。
**路由**: `utils.py` 中 `ai_solve_quiz()` / `ai_solve_quiz_image()` / `ai_grade_quiz_image()` 按 provider 分发。

### 7.1 Doubao API (doubao_api.py) — 默认

**类型**: HTTP API (OpenAI SDK, stateless, fast, 支持多模态)

**配置**: `data/passwords/doubao.txt`
```
ARK_API_KEY="ark-..."
model="ep-xxxxxxxxxxxxx"
```

**API 端点**: `https://ark.cn-beijing.volces.com/api/v3`

#### 公共接口

```python
def doubao_solve_quiz(questions_text, course_name, section_name, timeout=180) → list[{index, answer}]
  # 纯文本模式: 单个 user message → chat.completions.create
  # 温度: 0.1

def doubao_solve_quiz_image(image_paths, course_name, section_name, timeout=180) → list[{index, answer}]
  # 多模态模式: text prompt + N 张 base64 图片
  # 所有图片在单次 API 调用中发送

def doubao_ask_image(image_paths, prompt, timeout=180) → str
  # 通用多模态查询 (Phase C 批改使用)
  # 返回原始文本，不解析 JSON
```

#### 重试策略

```python
RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
# 指数退避: 2s → 4s → 8s (max 3 retries)
# 非重试: AuthenticationError, BadRequestError
```

#### 答案解析

```python
_parse_quiz_answer(text) → list[dict]
  # 1. 去除 markdown code fences
  # 2. 尝试直接 JSON.parse
  # 3. 括号深度跟踪提取
  # 4. 正则回退
  # → _normalize_answer_keys() 标准化 {index, answer}

_normalize_answer_keys(answers) → list[{index, answer}]
  # 兼容 index/id/num/n + answer/ans/text
```

### 7.2 DeepSeek Web (deepseek_web.py)

**类型**: 浏览器自动化 (stateful, slow)

**会话**: `deepseek` (独立持久化 Chrome)

**标签页**:
- Tab 0: 文本模式 (快速模式 + 深度思考 + 智能搜索)
- Tab 1: 识图模式 (上传图片 + 深度思考)

#### 公共接口

```python
def ensure_deepseek_ready() → bool
  # Tab 0: 确保浏览器打开 + 登录 + 新鲜对话页 + 开关设置

def ensure_deepseek_image_ready() → bool
  # Tab 1: 确保浏览器打开 + 登录 + 新鲜对话页

def deepseek_solve_quiz(questions_text, course_name, section_name) → list[{index, answer}]
  # Tab 0 文本模式: ask_deepseek() → parse JSON

def deepseek_solve_quiz_image(image_paths, course_name, section_name) → list[{index, answer}]
  # Tab 1 识图模式: ask_deepseek_image() → parse JSON

def ask_deepseek(question, timeout=120) → str
  # 发送问题 → JS innerText 轮询等待 → 稳定后取最后的 JSON 数组

def ask_deepseek_image(image_paths, prompt, timeout=180) → str
  # 切换识图模式 → setInputFiles 上传 → 填 prompt → 发送 → 等待答案
```

#### 关键内部函数

| 函数 | 说明 |
|------|------|
| `_ds(*args)` | playwright-cli deepseek 会话调用 |
| `_ds_fill_js(text)` | JS 填充 (绕过 Shell 引号转义) |
| `_ds_run_code_file(js_code)` | 安全 JS 执行 (temp file + shell=False) |
| `_is_toggle_on_via_js(label)` | JS 检测开关状态 |
| `_ensure_toggle_on(label)` | 确保开关开启 (最多3次点击) |
| `_find_last_json_array(text)` | 从末尾扫描取最后一个有效 JSON 数组 |
| `_detect_blocking(page_text)` | 检测验证码/限流/服务不可用 |

#### 阻塞检测模式

```python
_BLOCKING_PATTERNS = [
    (验证码): 请输入验证码 / 安全验证 / 滑块验证
    (限流): 操作频繁 / 请求过多 / rate limit
    (服务故障): 服务不可用 / service unavailable
    (会话过期): 登录失效 / 重新登录
    (HTML页面): <html / <!DOCTYPE (错误重定向)
]
→ raise DeepSeekBlockedError(reason, page_snippet)
```

#### 上传验证

上传后 JS 验证:
- blob URL 计数
- data URI 计数
- attachment 元素计数
- 文件名匹配
- **失败则拒绝发送** (避免纯文本提示以识图模式发送)

---

## 8. JavaScript 注入接口

所有 JS 通过 `_run_js_file()` 或 `pw_run_code_file()` 注入到浏览器页面。

### 8.1 JS 文件列表

| 文件 | 用途 | 目标 iframe | 状态 |
|------|------|------------|------|
| `_decrypt_font.js` | Typr.js + MD5 字体解密 | quiz doHomeWorkNew | 使用中 |
| `_v17_section_player.js` | 视频/音频/文档播放器 (inline chaining) | mooc2-ans | **主播放器** |
| `_v11_phase2_fallback.js` | 视频顺序播放控制 (旧版) | mooc2-ans | 保留 |
| `_v10_js_combined.js` | 视频播放控制 (更旧版) | mooc2-ans | 保留 |
| `_resize_vp.js` | 视口缩放 2048×1152 | 主页 | 使用中 |
| `_debug_innertext.js` | 调试 innerText 提取 | — | 调试用 |
| `_table.json` | 字体映射表 (355KB) | (数据文件) | 使用中 |

### 8.2 内联 JS 模式

所有内联 JS 函数签名统一为:
```javascript
async (page) => {
    // page = Playwright Page 对象
    // 返回 JSON.stringify({...})
}
```

#### 常用 JS 模式

**iframe 查找**:
```javascript
const iframe = page.frames().find(f =>
    f !== page.mainFrame() &&
    f.url().includes('TARGET_URL_PATTERN')
);
```

**DOM 遍历 + 数据提取**:
```javascript
const els = iframe.locator('CSS_SELECTOR').all();
for (const el of els) {
    const text = await el.innerText();
    const attr = await el.getAttribute('attr_name');
}
```

**元素截图**:
```javascript
await el.scrollIntoViewIfNeeded();
await el.screenshot({path: '...'});
```

**iframe 内 evaluate**:
```javascript
const result = await iframe.evaluate((tableJson) => {
    return window._cxDecryptFont(document, tableJson);
}, tableJsonStr);
```

**问题边界检测** (`.newZy_TItle` / `.Zy_TItle`):
```javascript
const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
for each titleEl → boundingBox() → sort by Y → merge within 10px → build boundaries
```

### 8.3 内联 JS 注入点

| 位置 | 用途 | 场景 |
|------|------|------|
| `chaoxing_login()` | 登录表单填充 + 提交 | 每次登录 |
| `_ensure_on_course_listing()` | 点击 课程 菜单 | 课程发现前 |
| `scan_courses()` | 课程卡片解析 | 扫描未完成课程 |
| `scan_course_sections()` | 章节树 DOM 提取 | 章节扫描 |
| `open_course()` / `navigate_to_section()` | 点击 章节 tab + 小节链接 | 导航 |
| `_capture_question_screenshots_v2()` | .TiMu 容器截图 + 元数据 | AI 答题 |
| `_capture_filled_screenshots_v2()` | 填充后截图 | Phase C 批改 |
| `_click_option_dom()` | 容器隔离选项点击 | 答案填充 |
| `decrypt_font_cxsecret()` | 字体解密 | Tab0 文本模式 |
| `_detect_question_types()` | 题型检测 (radio/checkbox) | 填充分发 |
| `_submit_quiz_native()` | 原生表单提交 | 提交答案 |
| `ensure_chaoxing_viewport()` | 视口调整 | 截图前 |

---

## 9. 配置与状态文件格式

### 9.1 主配置: `backend/chaoxing_config.json` *(共享路径，由 `chaoxing/config.py` 读取)*

```json
{
  "session": "chaoxing-chrome",
  "playwright_cli": "playwright-cli.cmd",
  
  "ai": {
    "provider": "doubao-api",          // "doubao-api" | "deepseek-web"
    "doubao": {
      "model": "ep-xxxxxxxxxxxxx",
      "base_url": "https://ark.cn-beijing.volces.com/api/v3",
      "timeout": 180,
      "max_retries": 3,
      "retry_base_delay": 2
    },
    "deepseek_session": "deepseek",
    "deepseek_timeout": 180
  },
  
  "courses": [
    {
      "name": "概率论与数理统计",
      "priority": 1,
      "courseid": "255106367",
      "clazzid": "127207872",
      "cpi": "415409200",
      "current_progress": 79, "total_tasks": 100,
      "remaining_quiz_sections": [{chapter, section, name, tasks}],
      "remaining_content_sections": [{chapter, section, name, tasks}],
      "chapters": [{num, name, sections, tasks_per}]
    }
  ],
  
  "timeouts": {
    "page_load": 30, "video_watch": 60,
    "quiz_answer": 120, "section_complete": 15,
    "snapshot": 15, "click_action": 10
  },
  
  "retry": {
    "quiz_max_retries": 10,
    "quiz_target_score": 100,
    "section_max_retries": 3
  }
}
```

### 9.2 凭证文件

**`data/passwords/chaoxing.txt`** — 超星多账户:
```
{
    website:"https://passport2.chaoxing.com/login?..."
    account[0]:手机号
    password[0]:密码
}
```

**`data/passwords/pwd.txt`** — DeepSeek 账号:
```
{
    网站:https://chat.deepseek.com/
    账号:手机号
    密码:密码
}
```

**`data/passwords/doubao.txt`** — 豆包 API 密钥:
```
ARK_API_KEY="ark-..."
model="ep-xxxxxxxxxxxxx"
```

### 9.3 运行时产物

| 文件 | 目录 | 格式 | 说明 |
|------|------|------|------|
| `progress_state[_session].json` | `data/output/` | `{completed_sections: ["课名::X.Y"], completed_courses: ["课名"], errors: [...]}` | 进度追踪 |
| `discovered_courses[_session].json` | `data/output/` | `[{name, courseid, clazzid, cpi, ...}]` | 课程发现快照 |
| `_quiz_stats_<course>.json` | `data/output/` | `{course_name, records: [{section, score, mode, ...}]}` | 答题统计 |
| `tmp*.js` | `data/temp/` | JavaScript | 临时脚本 (自动清理) |
| `_quiz_q*[_session].png` | `data/temp/` | PNG | 题目截图 (批次前清理) |
| `_quiz_filled_q*[_session].png` | `data/temp/` | PNG | 填充后截图 (批次前清理) |
| `_captcha_img*.png` | `data/temp/` | PNG | 验证码截图 |
| `chaoxing_YYYYMMDD.log` | `data/logs/` | 文本 | 按日滚动日志 |

### 9.4 Session 命名约定

| Session 名 | 用途 |
|-----------|------|
| `chaoxing-chrome` | 默认单账户超星会话 |
| `chaoxing-chrome-0`, `chaoxing-chrome-1`, ... | 多账户独立会话 |
| `deepseek` | 共享 DeepSeek 会话 |

### 9.5 控制文件

| 文件 | 创建者 | 消费者 | 说明 |
|------|--------|--------|------|
| `.pause_flag` | PS1 KB 监视器 (P键) | Python `check_pause()` | 暂停信号 |
| `.quit_flag` | PS1 KB 监视器 (Q键) | Python `check_pause()` | 退出信号 |

---

## 10. CLI ↔ Python 通信协议

### 10.1 进程启动

```
PS1 Start-Process
  ├── FileName: python (or python3)
  ├── Arguments: -u "script_path" "arg1" "arg2" ...
  ├── UseShellExecute: false
  ├── RedirectStandardOutput: true
  ├── RedirectStandardError: true
  └── EnvironmentVariables:
      ├── CHAOXING_HEADED = "1" | "0"
      ├── CHAOXING_WORKSPACE = <root>
      ├── PYTHONIOENCODING = "utf-8"
      └── PYTHONUTF8 = "1"
```

### 10.2 stdout 协议

| 行格式 | 方向 | 说明 |
|--------|------|------|
| `[HH:MM:SS] [LEVEL] [thread] message` | Python → stdout | 通用日志 |
| `PROGRESS:[N] current/total message` | Python → stdout | 进度更新 |
| `STATUS:[N] running=X [progress=Y/Z course_count=W]` | Python → stdout | 状态查询 |
| `[EXEC] python -u script args` | PS1 → stdout | 执行前日志 |
| `[STDERR] line` | PS1 → stdout | 错误输出转写 |
| `[CLI] message` | PS1 → stdout | CLI 层消息 |

### 10.3 特殊输出标记 (PS1 解析)

```powershell
# batch-test 内联登录脚本输出
"LOGIN_OK:True" / "LOGIN_OK:False"
"COURSE_IDS:courseid=X|clazzid=Y|cpi=Z"

# _batch_nav.py 输出
"NAV_OK:True" / "NAV_OK:False"
"NAV_ERROR:empty_ids"
"has_quiz=True"

# _test_phase_c.py 输出
"PASSED!"
"Accuracy: XX%"
```

### 10.4 PS1 事件驱动解析

```powershell
# Progress 模式: OutputDataReceived 事件处理
if ($line -match '^PROGRESS:\[(\d+)\]\s+([\d-]+)/([\d-]+)\s+(.+)$') {
    # 渲染进度条 [########------------] XX%
}
if ($line -match '\[ERROR\]') { # 红色输出 }
if ($line -match '\[WARN\]')  { # 黄色输出 }

# Normal 模式: 逐行 Write-Host $line

# 3分钟超时检测:
if (elapsed >= 3min && !warned) {
    Write-Host "[⚠] No progress — 可能卡住"
}
```

### 10.5 优雅关闭协议

```
CLI 层 (Q键按下):
  → $sync.Quit = $true
  → create .quit_flag
  → Python while 循环: if ($sync.Quit) break
  → proc.WaitForExit(30000) → if not exited: proc.Kill()

Python 层 (check_pause 调用点):
  → 检测 .quit_flag → unlink → raise KeyboardInterrupt
  → 外层捕获 → SHUTDOWN_FLAG.set() → save state → return
```

### 10.6 多账户并发模型

```
PS1 --all-accounts:
  → 主线程: Start-KeyboardMonitor (独立 Runspace)
  → 主线程: Invoke-PythonScript chaoxing_orchestrator.py --all-accounts
  → Python 主线程: 解析账号列表 → 创建 N 个 Thread
     每个 Thread: run_for_account(idx, cred, args)
         → set_active_session(f"chaoxing-chrome-{idx}")
         → 独立浏览器会话

PS1 batch-test --all-accounts:
  → 主线程: 创建 N 个 Runspace
     每个 Runspace: Invoke-BatchTestSingleAccount(idx)
         → 内联 Python 登录脚本
         → _batch_nav.py 导航
         → _test_phase_c.py 测试
  → barrier: 等待所有 Runspace 完成
  → 汇总结果
```

---

## 附录 A: 常用 URL 模式

| 页面 | URL 模式 |
|------|----------|
| 登录页 | `https://passport2.chaoxing.com/login` |
| 个人空间 | `https://i.chaoxing.com/base` |
| 课程列表 (iframe) | `.../visit/interaction` |
| 课程页 | `https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=...` |
| 章节树 (iframe) | `https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse?...` |
| 答题页 (iframe) | `.../mooc-ans/work/doHomeWorkNew` 或 `.../knowledge/cards` |
| 学习页 | `https://mooc1.chaoxing.com/mooc-ans/.../studentstudy?...` |

## 附录 B: 关键 DOM 选择器

| 选择器 | 页面 | 用途 |
|--------|------|------|
| `div.course.learnCourse[id^="c_"]` | 课程列表 | 课程卡片 |
| `div.chapter_item` | 章节树 | 章节/小节项 |
| `.catalog_num em` | 章节树 | 章节编号 |
| `.catalog_sbar` | 章节树 | 小节编号 (X.Y) |
| `.catalog_state.icon_yiwanc` | 章节树 | 已完成标记 |
| `.TiMu` | 答题页 | 题目容器 (zy/ks 类型) |
| `.questionLi` | 答题页 | 题目容器 (zj 类型) |
| `.newZy_TItle, .Zy_TItle` | 答题页 | 题号元素 (问题边界) |
| `[class*="before-after"]` | 答题页 | 选项元素 (TiMu) |
| `.answerBg` | 答题页 | 选项元素 (questionLi) |
| `input[id^="answer"]` | 答题页 | 隐藏答案值 |
| `.check_answer, .check_answer_dx` | 答题页 | 绿色对勾标记 |
| `a.clicktitle span` | 章节树 | 章节/小节名称 |

## 附录 C: 错误处理层级

```
Level 1 — PS1: 进程启动失败 / Python 未安装 / playwright-cli 未安装
Level 2 — Python Orchestrator: 登录失败 / 课程发现失败 / 线程异常
Level 3 — Quiz Solver: AI 无应答 / 导航失败 / 提交失败 → 重试 (最多5次)
Level 4 — utils.py: playwright-cli 超时 / snapshot 解析异常 / 字体解密异常
Level 5 — AI: API 错误 (重试) / 限流 (等待) / 验证码 (人工介入)
```

每个层级有独立的错误日志和恢复策略，上层不因下层异常而崩溃。
