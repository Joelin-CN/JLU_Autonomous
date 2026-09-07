# DeepSeek 自动解题模块 — 修复报告

> 日期: 2026-06-23 | 文件: `scripts/deepseek_web.py` | 总计: 11 项修复

## 修复清单 (11项)

### 致命 Bug (阻塞功能)

| # | Bug | 根因 | 修复 |
|---|-----|------|------|
| 1 | 消息发送失败 | `_find_ref("发送")` 匹配到输入框 placeholder `"给 DeepSeek 发送消息"` | 改用 `_ds_press("Enter")` 发送 |
| 2 | 等待循环立即退出 | `"深度思考" in snap` 匹配到输入区 toggle 标签（永远存在） | 改用 JS `body.innerText` 轮询，不再检查 snapshot |
| 3 | 取到 Prompt 模板 JSON | Prompt 中包含 JSON 格式示例，`find('[')` 取到第一个 `[` | 新增 `_find_last_json_array()` 反向扫描 |
| 4 | Shell 中文/引号损毁 | `_ds_fill` 通过 `cmd.exe shell=True`，`"` 和中文被破坏 | 新增 `_ds_fill_js()` 用 JS `locator.fill()` 绕过 shell |

### 中危 Bug (结果错误)

| # | Bug | 根因 | 修复 |
|---|-----|------|------|
| 5 | 流式答案截断 | 检测到合法 JSON 立即 `break`，取到中间态 | 改为稳定后取最后合法 JSON |
| 6 | JSON key 丢失 | AI 返回 `id` 而非 `index`，下游 `_click_option` 找不到题号 | 新增 `_normalize_answer_keys()`，`id`/`q_index`→`index` |
| 7 | 深度思考状态误判 | 背景色检测覆盖了 `aria-pressed="false"` | ARIA 属性优先 + CSS 后缀精确匹配 `--selected` |

### 逻辑优化 (冗余/浪费)

| # | 改进 | 修改前 | 修改后 |
|---|------|--------|--------|
| 8 | 页面重复刷新 | `has_history` 包含 `'深度思考'` toggle 标签 → 永远 True | 移除，ref 阈值 40→80 |
| 9 | `ensure_deepseek_image_ready` 无缓存 | 每次调用都 goto→切模式 | 新增 `_state['tab1_configured']` 缓存 |
| 10 | 识图 radio 点击不准 | `_find_ref` 取到内部 generic text (e61) 而非 radio (e54) | 正则 `radio "识图模式" [ref=e54]` 精确匹配 |

---

## 当前架构

```
deepseek_web.py
├── Session 管理
│   ├── is_deepseek_open()
│   ├── ensure_deepseek_ready()        → Tab 0: 快速模式+深度思考+智能搜索
│   └── ensure_deepseek_image_ready()  → Tab 1: 识图模式+深度思考
│
├── 核心交互
│   ├── ask_deepseek()          → Tab 0 文本问答
│   │   └── _ds_fill_js() → Enter → innerText轮询 → _find_last_json_array()
│   ├── ask_deepseek_image()    → Tab 1 图片问答
│   │   └── JS上传图片 → _ds_fill_js() → Enter → innerText轮询 → _find_last_json_array()
│   │
│   ├── deepseek_solve_quiz()        → 封装 ask_deepseek + prompt模板 + _parse_quiz_answer
│   └── deepseek_solve_quiz_image()  → 封装 ask_deepseek_image + prompt模板 + _parse_quiz_answer
│
├── Toggle 系统
│   ├── _is_toggle_on_via_js()   → ARIA优先 → data-state → CSS后缀 → 背景色
│   └── _ensure_toggle_on()      → 检测+点击+重检闭环 (最多3次)
│
├── JSON 解析
│   ├── _find_last_json_array()  → 反向扫描取最后合法 JSON (跳过prompt模板)
│   ├── _parse_quiz_answer()     → 去markdown fence + bracket-depth提取
│   └── _normalize_answer_keys() → id→index, answer_text→answer 等归一化
│
└── 状态缓存 (_state dict)
    ├── tab0_configured   → 文本模式已配置
    ├── tab1_configured   → 识图模式已配置
    └── _toggle_debugged_* → toggle首次检测日志
```

---

## 调用链路（生产环境）

```
chaoxing_orchestrator.py
  └── chapter_quiz_solver.py  → ChapterQuizSolver.solve_quiz()
        ├── get_decrypted_quiz_text()     → 字体解密 → 文本模式
        │   └── utils.ai_solve_quiz()
        │       └── deepseek_web.deepseek_solve_quiz()
        │           └── ask_deepseek() → Tab 0
        │
        └── _capture_question_screenshots()  → 逐题截图 → 识图模式
            └── utils.ai_solve_quiz_image()
                └── deepseek_web.deepseek_solve_quiz_image()
                    └── ask_deepseek_image() → Tab 1
```

---

## 凭据位置

- DeepSeek: `passwords/pwd.txt` (chat.deepseek.com)
- Chaxing 账号: 配置在 `scripts/chaoxing_config.json`

## 已知未修复项

1. `ask_deepseek_image` 内部的 `ensure_deepseek_image_ready()` 调用与外部调用者可能重复（缓存已缓解）
2. `_ds_fill_js` 使用的 `locator.fill()` 对 contenteditable div 可能不生效（当前 DeepSeek 用的是 textarea，正常）
3. `_fill_via_clipboard` PowerShell here-string 对含 `$` `"@` 的文本有风险（仅作 fallback）
4. ✅ `_ensure_image_mode_with_toggles()` 已删除 (2026-06-23) — mode switch 已完全迁移到 `ask_deepseek_image()` 内部。

## 测试脚本

- `scripts/test_deepseek_solve.py` — 文本模式单题测试
- `scripts/test_deepseek_image.py` — 识图模式 3 题测试（含 conda base 生成模拟试卷）
- `scripts/test_normalize.py` — JSON 归一化单元测试

---

## Bug #11: 识图模式图片未正确附加（纯文本被注入）

> 发现: 2026-06-23 | 状态: ✅ 已修复

### 症状
`ask_deepseek_image()` 上传图片后，DeepSeek 收到的只有 prompt 文本，没有图片。
日志显示 `Thumbnails not confirmed, proceeding anyway...`

### 根因
`_ensure_image_mode_with_toggles()` 点击 识图 radio → DeepSeek 自动弹出文件选择器 → 
代码立即按 `Escape` 关闭文件选择器 → 页面处于"已切换模式但文件选择器已关闭"的半切换状态 →
`ask_deepseek_image()` 尝试通过 attach 按钮上传，但 ref 找不到 → 回退到 JS `setInputFiles` →
文件 input 处于不确定状态 → 图片未能正确附加到对话。

### 修复
1. **`_ensure_image_mode_with_toggles()`** (L356): 移除 `_ds_press('Escape')` — 不再关闭文件选择器
2. **`ensure_deepseek_image_ready()`** (L851-861): 不再在此处调用 `_ensure_image_mode_with_toggles()` — 仅负责浏览器/登录/标签页环境，保持页面在 clean text mode
3. **`ask_deepseek_image()`** (L894-915): 新增原子化的 mode switch + upload 流程 — 点击识图 radio → 文件选择器打开 → 立即用 `setInputFiles` 满足文件选择器 → 上传图片 → 验证缩略图

### 修复后流程
```
ask_deepseek_image()
  ├─ ensure_deepseek_image_ready()  → 浏览器+登录+Tab1+clean page
  ├─ 点击 识图 radio               → 文件选择器打开
  ├─ setInputFiles([img1,img2,img3]) → Playwright 满足文件选择器
  ├─ 验证缩略图已出现
  ├─ _ds_fill_js(prompt) + Enter
  └─ innerText 轮询 → _find_last_json_array()
```
