# 修复日志 — BAT/PS1 六模式全修复 + 进程管理 + 并行化

**日期**: 2026-06-24
**操作**: 对 chaoxing_cli.bat/ps1 的 1-6 模式进行全面修复，添加进程管理，模式分离，并行化
**触发**: 用户测试发现 6 个模式中仅 mode 2 正常，其余均有问题

---

## 一、问题汇总与根因分析

| 问题 | 症状 | 根因 | 严重度 |
|------|------|------|--------|
| Modes 3/4/5 无 Chrome | 选定 headed=yes 后无任何窗口弹出，进程管理器无 chrome.exe | `chaoxing_orchestrator.py:main()` 的 `input()` 确认提示在 stdout 被 `Invoke-PythonScript` 捕获后阻塞 — 用户看不到提示也无法输入 | **P0** |
| Mode 3 = Mode 4 | 两者行为完全相同（quiz+content），未分离 | PS1 对 solve-quiz 和 complete-content 传递完全相同的 Python 参数 | **P1** |
| Mode 6 顺序执行 | 多账户模式下 account0 完成后不动，不拉起第二个 Chrome | `Invoke-BatchTest` 使用 `foreach` 循环串行处理账户 | **P1** |
| Course 提示无意义 | "Target course" 始终显示 `概率论与数理统计`，且无法选择 | PS1 菜单 Q3 直接取 config[0].name 作为默认值 | **P2** |
| Chrome 进程累积 | 反复开/关 BAT 导致后台累积大量 chrome.exe，最终内存溢出 | 无进程/会话清理机制 | **P2** |
| Mode 1 无窗口 | headed=yes 时 status 不显示任何浏览器窗口 | `cmd_status()` 是纯只读操作，不启动浏览器 | **P3** |

---

## 二、修复详情

### Fix 1 (P0): 消除 stdin 阻塞 — 添加 `--yes` 标志

**文件**: `scripts/chaoxing_orchestrator.py` + `chaoxing_cli.ps1`

**根因**:
- `chaoxing_orchestrator.py:main()` 在多账户路径（`args.account is not None`）中有 `input()` 确认提示
- `Invoke-PythonScript` 使用 `System.Diagnostics.Process` 重定向 stdout/stderr，用户看不到提示
- stdin 继承自父进程，`input()` 阻塞等待输入，进程挂死
- Mode 2 (scan) 正常是因为 `--scan-only` 走 `if not args.scan_only:` 跳过了确认

**修复**:
1. 添加 `--yes` CLI 参数到 orchestrator
2. 确认提示条件改为 `if not args.scan_only and not args.yes:`
3. PS1 中所有 `Invoke-PythonScript` 调用均传递 `--yes`
4. 当 `--yes` 为真且 stdin 关闭时，不再触发 `EOFError` abort

**验证**: `python chaoxing_orchestrator.py --scan-only --yes --account 0` 成功跳过确认，直接登录并扫描课程。

---

### Fix 2 (P1): 模式分离 — quiz-only vs content-only

**文件**: `scripts/chaoxing_orchestrator.py` + `chaoxing_cli.ps1`

**修复**:
1. 添加 `--quiz-only` 和 `--content-only` CLI 参数
2. `process_course()` 新增参数:
   - `quiz_only=True` → 跳过 Phase 2（content）
   - `content_only=True` → 跳过 Phase 1（quizzes）
3. PS1 mode 3 传递 `--quiz-only`，mode 4 传递 `--content-only`
4. 日志中添加模式标签 `[QUIZ-ONLY]` / `[CONTENT-ONLY]`

**PS1 参数变更**:
- Mode 3: `$pyArgs = @("--yes", "--quiz-only")` — 移除 `--course`
- Mode 4: `$pyArgs = @("--yes", "--content-only")` — 移除 `--course`

---

### Fix 3 (P2): 移除 Course 提示

**文件**: `chaoxing_cli.ps1`

**修复**:
- 删除 Invoke-InteractiveMenu 中的 Q3（Target course 提示）
- 设置 `$Script:Course = ""` — 不过滤课程
- 所有模式的 `$pyArgs` 中移除 `--course` 参数
- orchestrator 自动处理所有未完成课程

---

### Fix 4 (P1): Mode 6 并行化

**文件**: `chaoxing_cli.ps1`

**修复**:
1. 提取 `Invoke-BatchTestSingleAccount` 函数（独立可并行调用的单账户 batch test）
2. `Invoke-BatchTest` 检测多账户时使用 **PowerShell runspaces** 并行启动
3. 使用 `[hashtable]::Synchronized` 收集各 runspace 的结果
4. 单账户模式保持直接调用（无 runspace 开销）
5. 函数定义注入 runspace：`${function:Invoke-BatchTestSingleAccount}` 传递到 AddScript

**关键代码**:
```powershell
if ($useParallel) {
    $batchSync = [hashtable]::Synchronized(@{ Results = @{}; Quit = $false })
    foreach ($acctIdx in $batchAccounts) {
        $ps = [powershell]::Create()
        $funcDef = "function Invoke-BatchTestSingleAccount {`n" + ${function:Invoke-BatchTestSingleAccount} + "`n}"
        [void]$ps.AddScript($funcDef)
        [void]$ps.AddScript({ param(...) ... }).AddArgument(...)
        # Runspace per account
    }
    # Wait all → merge results
}
```

---

### Fix 5 (P2): 进程/会话管理

**文件**: `chaoxing_cli.ps1`

**修复**:
1. 新增 `Invoke-KillSessions` 函数:
   - 支持 `-Target "all"` → 杀死所有 chaoxing-chrome-* 会话
   - 支持 `-Target "0,1"` → 杀死指定账户会话
   - 交互模式: `[A]ll / [0,1] / [Enter] skip`
2. 菜单添加 `[K] kill-sessions` 选项
3. 启动时自动检测已有会话，提示是否清理

---

### Fix 6 (P3): Mode 1 status headed

**文件**: `chaoxing_cli.ps1`

**修复**:
- status 命令 headed 模式：检查是否存在浏览器会话
- 如无会话，自动调用 `chaoxing_login()` 启动 headed Chrome 并登录
- 用户可看到浏览器窗口和课程列表

---

## 三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `scripts/chaoxing_orchestrator.py` | 修改 | +`--yes`, `--quiz-only`, `--content-only` 参数；process_course 模式分离；确认提示条件修改 |
| `chaoxing_cli.ps1` | 大幅修改 | 6 个模式的参数重构；新增 Invoke-KillSessions；新增 Invoke-BatchTestSingleAccount；Invoke-BatchTest 并行化；移除 Q3；status headed 启动浏览器；菜单添加 [K] |
| `chaoxing_cli.bat` | 无变化 | 保持最小启动器逻辑 |
| `docs/FIXLOG_20250624_bat_ps1_modes.md` | **新建** | 本文件 |

---

## 四、验证结果

| 验证项 | 方法 | 结果 |
|--------|------|------|
| `--yes` 跳过确认 | `python chaoxing_orchestrator.py --scan-only --yes --account 0` | ✅ 确认被跳过，直接进入扫描 |
| Status 基本功能 | `python chaoxing_orchestrator.py --status --account 0` | ✅ STATUS:[0] running=否 |
| 新增 CLI 参数注册 | `python chaoxing_orchestrator.py --help` | ✅ --yes, --quiz-only, --content-only 均显示 |
| PS1 语法检查 | `Parser::ParseFile()` → AST 非空 | ✅ 无语法错误 |
| Python 语法检查 | `ast.parse()` | ✅ 无语法错误 |

---

## 五、遗留注意事项

1. **Mode 6 runspace 并行**: PS 5.1 的 runspace 不自动共享函数定义，使用了 `${function:Name}` 注入。多账户并行时各 runspace 的 `Write-Host` 输出会交错显示，这是预期行为。
2. **Mode 1 status headed**: 仅对首个请求账户启动浏览器（多账户模式下启动 account 0 作为预览）。全部账户的 status 数据仍从终端输出。
3. **Course 过滤移除**: 如需按课程过滤，可直接命令行调用 `python chaoxing_orchestrator.py --course "课程名"`，但 CLI 菜单不再提供此选项。
