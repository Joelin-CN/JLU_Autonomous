# 修复日志 — 后端重构验证 + 多账户 E2E 解题测试

**日期**: 2026-06-24  
**操作**: 验证重构后的 `chaoxing/` 后端包，编写多账户 E2E 测试，发现并修复循环导入Bug  
**前置上下文**: `scripts/` 单体拆分为 41 模块 `chaoxing/` 包后的首次真实浏览器全流程验证

---

## 一、测试环境

| 项目 | 值 |
|------|-----|
| Python | 3.13.6 (Win AMD64) |
| 浏览器 | Chrome (Playwright persistent, headed) |
| AI 后端 | Doubao/Volcano Ark API (`doubao-api`) |
| 账户 | 3 个（`passwords/chaoxing.txt`），测试使用 account[0] |
| 目标课程 | 概率论与数理统计（17 个测验章节，79/100 进度） |
| 重构跨度 | `scripts/` 单体 → `chaoxing/` 41 模块 12 子包 |

---

## 二、Phase A: 已有测试验证

### 2.1 单元测试 (`tests/unit/`)

```powershell
python -m pytest tests/unit/ -v -p no:capture
```

| 检查项 | 结果 |
|--------|------|
| 总测试数 | 66 |
| 通过 | ✅ 66/66 (100%) |
| 失败 | 0 |
| 测试文件 | `test_auth.py`(10) `test_browser_engine.py`(13) `test_config.py`(27) `test_exceptions.py`(5) `test_quiz_strategies.py`(7) `test_session.py`(5) |

**结论**: 重构后的 `chaoxing/` 包所有单元测试通过，无回归。

### 2.2 向后兼容 Shim 导入验证

| Shim 文件 | 导出符号 | 结果 |
|-----------|----------|------|
| `scripts/utils.py` | `cfg, log, pw_snapshot, pw_goto, chaoxing_login, ...` (40+ 符号) | ✅ |
| `scripts/chapter_quiz_solver.py` | `ChapterQuizSolver, QuizStats` | ✅ |
| `scripts/chapter_content_bot.py` | `ChapterContentBot, ProgressTracker` | ✅ |
| `scripts/deepseek_web.py` | `DeepSeekWebSolver, ask_deepseek, ...` (8 符号) | ✅ |
| `scripts/doubao_api.py` | `DoubaoAPISolver, doubao_solve_quiz, ...` (4 符号) | ✅ |

**结论**: 26 个旧测试脚本 (`tests/test_*.py`) 的 `from utils import ...` 导入模式不受影响。

### 2.3 旧测试脚本导入分析

抽查 5 个关键旧脚本的导入语句：

| 脚本 | 导入来源 | 兼容性 |
|------|----------|--------|
| `test_login_loop.py` | `utils` → cfg, log, pw_*, chaoxing_login, ... | ✅ |
| `test_doubao_api.py` | `doubao_api` → DoubaoAPISolver, doubao_solve_quiz | ✅ |
| `test_deepseek_diag.py` | `deepseek_web` → DeepSeekWebSolver, ask_deepseek, ... | ✅ |
| `test_captcha_flow.py` | `_solve_captcha` → detect_captcha, solve_captcha | ✅ |
| `test_normalize.py` | 无外部依赖 | ✅ |

**结论**: 旧测试脚本均可通过 shim 正常导入。

---

## 三、Phase B: 新建 E2E 测试

### 新增文件: `tests/e2e/test_multi_account_full_flow.py`

| 属性 | 值 |
|------|-----|
| 大小 | 23.7 KB, ~500 行 |
| 设计 | pytest + standalone 双模式 |
| 核心功能 | 多账户并行 → 登录 → 课程发现 → 测验答题 → 内容完成 |
| 报告输出 | `output/e2e_reports/e2e_account{N}_{timestamp}.json` + 聚合报告 |

**CLI 接口:**

```powershell
# 单账户扫描（只读，安全）
python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --scan-only

# 单账户完整流程（真实提交）
python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --course "概率论与数理统计"

# 所有账户并行
python tests/e2e/test_multi_account_full_flow.py --headed --all-accounts

# pytest 模式
pytest tests/e2e/test_multi_account_full_flow.py -v -s --headed --accounts 0 --scan-only
```

**pytest 选项:**

| 选项 | 说明 |
|------|------|
| `--headed` | 有头 Chrome（默认 on） |
| `--headless` | 无头模式 |
| `--accounts 0,1` | 逗号分隔账户索引 |
| `--all-accounts` | 所有账户并行 |
| `--course "名称"` | 按课程名过滤（子串匹配） |
| `--scan-only` | 仅扫描（只读） |
| `--dry-run` | 预览模式 |
| `--quiz-only` | 仅处理测验 |
| `--content-only` | 仅处理内容 |

**设计要点:**
- 直接使用 `chaoxing.orchestrator` 原语，不经过 `scripts/` 旧路径
- 线程局部会话隔离 (`chaoxing-chrome-N`)
- 优雅 Ctrl+C 关闭（`SHUTDOWN_FLAG`）
- 进度追踪 + resume 支持

---

## 四、Phase C: E2E 执行中发现的问题

### 4.1 扫描测试（只读）— 全部通过

```powershell
python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --scan-only
```

| 检查项 | 结果 |
|--------|------|
| 登录 132*** | ✅ 14 秒完成 |
| 课程发现 | ✅ 11 门未完成课程 |
| 章节扫描 | ✅ 大学物理ABC（下）7章29节、概率论 9章17测验+39内容、综合英语-2025 5章20节 |
| JSON 报告 | ✅ `output/e2e_reports/e2e_account0_*.json` |
| 错误数 | 0 |

**耗时**: 0.9 分钟

---

### 4.2 解题测试 — 发现 P0 循环导入Bug

```powershell
python tests/e2e/test_multi_account_full_flow.py --headed --all-accounts --quiz-only --course "概率论与数理统计"
```

第一轮执行中，3 个账户的测验 1.6 全部在 `_solve_batched()` 阶段抛出:

```
[Batched] Batch 1/6 exception: maximum recursion depth exceeded
[Batched] Batch 2/6 exception: maximum recursion depth exceeded
...
```

5 层策略全部失败后回退到 `Quiz already completed or empty, marking done`，测验被静默跳过。

---

### Fix 1 (P0): 循环导入导致 `maximum recursion depth exceeded`

- **文件**: `chaoxing/ai/doubao.py`（核心修复）、`scripts/doubao_api.py`（shim 不变）
- **症状**: 所有 AI 解题调用（文本/图片/评分）抛出 `RecursionError: maximum recursion depth exceeded`
- **调用链**（死循环）:
  ```
  ChapterQuizSolver._solve_batched()
    → ai_solve_quiz_image()                       [chaoxing/ai/router.py:61]
      → DoubaoAPISolver.solve_quiz_image()         [chaoxing/ai/doubao.py:37]
        → from doubao_api import doubao_solve_quiz_image  [scripts/doubao_api.py shim]
          → from chaoxing.ai.doubao import doubao_solve_quiz_image  [shim 重导出]
            → from doubao_api import doubao_solve_quiz_image  ← 死循环!
  ```
- **根因**: 重构时将真实实现留在 `scripts/doubao_api.py.bak`，shim `scripts/doubao_api.py` 只是重导出。`chaoxing/ai/doubao.py` 的类方法和模块级函数都通过 `_ensure_scripts_on_path()` + `from doubao_api import ...` 调用 shim，而 shim 又导入回 `chaoxing.ai.doubao`。
- **修复方案**: 将 `scripts/doubao_api.py.bak`（18.7KB，559 行）的真实实现完整迁移到 `chaoxing/ai/doubao.py`：
  - 所有私有函数（`_load_credentials`, `_create_client`, `_encode_image_to_base64`, `_build_text_prompt`, `_build_image_prompt`, `_call_chat_completion`, `_normalize_answer_keys`, `_parse_quiz_answer`）→ 直接写在模块内
  - 公共 API（`doubao_solve_quiz`, `doubao_solve_quiz_image`, `doubao_ask_image`）→ 模块级函数
  - `DoubaoAPISolver` 类方法 → 直接委托给同名模块级函数，不再通过 `from doubao_api import ...`
  - 删除 `_ensure_scripts_on_path()` 辅助函数
- **验证**:
  ```python
  # 确认源文件中无循环导入模式
  "from doubao_api import" not in chaoxing/ai/doubao.py  # ✅ True
  
  # Shim 函数 IS 模块函数（非额外包装）
  from scripts.doubao_api import doubao_solve_quiz_image as shim_fn
  from chaoxing.ai.doubao import doubao_solve_quiz_image
  shim_fn is doubao_solve_quiz_image  # ✅ True
  ```
- **影响范围**: 所有使用 `doubao-api` 的 AI 功能（quiz solving, grading, ask_image）
- **副作用**: 无。`scripts/doubao_api.py` shim 继续保持向后兼容，旧脚本无需修改。

### 修复后验证

修复后重新运行单账户解题测试：

```powershell
python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --quiz-only --course "概率论与数理统计"
```

| 检查项 | 结果 |
|--------|------|
| 登录 | ✅ |
| 课程发现 | ✅ 1 门课程（概率论与数理统计 79/100） |
| 测验 1.6 截图 | ✅ V2 策略 30/30 题截图 |
| AI 解题 (Doubao) | ✅ 6 批次，30/30 答案 |
| 答题填充 | ✅ 30/30 DOM 点击填入 |
| 提交 | ✅ `btnBlueSubmit` 正常提交 |
| 单元测试（修复后） | ✅ 66/66 通过 |

**AI 调用详情:**

| 批次 | 题目 | Token (prompt/compl/total) | 耗时 |
|------|------|---------------------------|------|
| 1/6 | Q1-5 | 6,781 + 671 = 7,452 | 22.7s |
| 2/6 | Q6-10 | 6,702 + 1,385 = 8,087 | 37.2s |
| 3/6 | Q11-15 | 6,781 + 663 = 7,444 | 12.4s |
| 4/6 | Q16-20 | 6,749 + 514 = 7,263 | 18.4s |
| 5/6 | Q21-25 | 6,778 + 719 = 7,497 | 18.5s |
| 6/6 | Q26-30 | 6,805 + 972 = 7,777 | 24.0s |
| **总计** | **30 题** | **~45,520** | **~133s** |

---

### Fix 2 (P1): 同类型循环导入 — `chaoxing/ai/deepseek.py`

- **文件**: `chaoxing/ai/deepseek.py`
- **症状**: 与 Fix 1 相同的调用链模式。当前未激活（AI provider = `doubao-api`），但切换到 `deepseek-web` 后会触发相同 bug。
- **根因**: `DeepSeekWebSolver` 的类方法通过 `_ensure_scripts_on_path()` + `from deepseek_web import ...` 调用 shim `scripts/deepseek_web.py`，而 shim 又重导出回 `chaoxing.ai.deepseek`。
- **修复方案**: 同 Fix 1 — 将 `scripts/deepseek_web.py.bak`（57KB）的真实实现迁移到 `chaoxing/ai/deepseek.py`，删除 `from deepseek_web import ...` 模式。
- **状态**: ⚠️ 已检测确认，待修复（deepseek-web 非活跃 provider，优先级 P1）
- **检测方式**: `"from deepseek_web import" in chaoxing/ai/deepseek.py` → `True`

---

## 五、发现的遗留问题（非本次引入）

### 5.1 提交后成绩解析返回 None%

- **位置**: `chaoxing/solvers/quiz/solver.py` → `_parse_score()`
- **症状**: 测验 1.6 提交 confirm 对话框后，`Score: None%`
- **推测原因**: 提交后跳转的结果页面 DOM 结构与解析逻辑不匹配
- **影响**: 无法判断是否需要重试，retry 逻辑依赖分数判断
- **优先级**: P1

### 5.2 后续章节导航 iframe 丢失

- **位置**: `chaoxing/solvers/quiz/solver.py` → `navigate_to_section()` / `go_back_to_chapter_tree()`
- **症状**: Quiz 1 完成后，Quiz 2-17 全部 `no-iframe`，无法找到 `mooc2/studentcourse` iframe
- **推测原因**: `go_back_to_chapter_tree()` 返回课程页面后 iframe 未完成重载，2 秒等待不够
- **复现**: Quiz 1.6 submit → `go_back_to_chapter_tree()` → Quiz 1.7 `no-iframe`
- **优先级**: P0（阻塞多章节连续答题）

### 5.3 字体解密 Tier 1 始终失败

- **位置**: `chaoxing/solvers/quiz/strategies.py` → `FontDecryptTextStrategy`
- **症状**: `Font decrypt failed: decrypt-func-not-loaded` — 所有测验都回退到 Tier 2 (V2Screenshot)
- **影响**: 每个测验浪费 ~7s（Tier 1 尝试 + 失败）→ 回退到 Tier 2 才正常工作
- **优先级**: P2（有可靠回退，不影响功能）

---

## 六、文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `chaoxing/ai/doubao.py` | **重写** | 从 shim 导入模式改为包含完整实现（~460 行），消除循环导入 |
| `tests/e2e/test_multi_account_full_flow.py` | **新建** | 多账户全流程 E2E 测试（~500 行），pytest + standalone 双模式 |
| `docs/changelogs/FIXLOG_20250624_e2e_backend_verify.md` | **新建** | 本文件 |

### 未修改的关键文件

| 文件 | 原因 |
|------|------|
| `scripts/doubao_api.py` | Shim 保持不变 — 已经是正确的重导出模式 |
| `scripts/utils.py` | 向后兼容 shim — 已验证 40+ 符号正确导出 |
| `scripts/chapter_quiz_solver.py` | Shim 保持不变 |
| `chaoxing/ai/router.py` | 路由逻辑正确，无需修改 |
| `tests/unit/*` | 66/66 通过，无回归 |

---

## 七、测试统计

| 指标 | 数值 |
|------|------|
| 测试总耗时 | ~15 分钟（含扫描 1min + 解题测试 ~10min + 单元测试） |
| 单元测试 | 66 通过 / 0 失败 |
| 旧脚本兼容性 | 5/5 导入通过 |
| Shim 验证 | 5/5 模块导出正确 |
| AI API 调用（修复后） | 6 批次 / 30 题 / ~45K tokens |
| 新发现 P0 | 1（循环导入 — 已修复） |
| 新发现 P1 | 1（deepseek.py 同类 bug — 已检测） |
| 遗留 P0 | 1（章节间导航 iframe 丢失） |
| 遗留 P1 | 1（成绩解析 None%） |
| 遗留 P2 | 1（字体解密 Tier 1 失败） |

---

## 八、后续建议

1. **P0**: 修复 `go_back_to_chapter_tree()` → `navigate_to_section()` 的 iframe 重载时序问题
2. **P1**: 修复 `_parse_score()` 以正确解析提交后成绩页面
3. **P1**: 将 `scripts/deepseek_web.py.bak` 实现迁移到 `chaoxing/ai/deepseek.py`（同 Fix 1 模式）
4. **P2**: 排查 `decrypt-func-not-loaded` — Typr.js 字体解密库加载失败
5. **增强**: 为 `navigate_to_section()` 添加 iframe 就绪等待 + 重试机制
6. **增强**: E2E 测试添加 `--headed --all-accounts --quiz-only` 多账户并行解题模式
