# Fix Log — 2026-06-23

## Session: CLI Panel Restructuring + Multi-Account + Status Output

---

### Fix 1: Panel Restructuring — Account First, Headed for All

**Before:** 
- Account scope only asked for `full-auto`
- Headed only asked for `full-auto` + `batch-test` (solve-quiz silently defaulted to No)
- Course prompt confusing: numbered list `[1] 概率论... [2] 大学物理...`

**After:**
- Q1: Account scope for ALL 6 commands — `[A]` all / `0,2` comma-list / Enter=default
- Q2: Headed for ALL 6 commands (fixes solve-quiz headed bug)
- Q3: Course — simplified prompt `Target course (Enter = first in config)`

**Files:** `chaoxing_cli.ps1` Invoke-InteractiveMenu (lines 458-610)

---

### Fix 2: Status [1] — New `--status` Flag + Formatted Table

**Before:** Status ran `--scan-only` which dumped full course trees.

**After:**
- New `cmd_status()` in orchestrator: reads accounts → checks browser sessions → scans courses → outputs `STATUS:[N] running=是/否 progress=X/Y course_count=N`
- PS1 parses STATUS lines → formatted table with Account/Running/Progress/Courses columns + auto-calculated percentage

**Files:** `chaoxing_orchestrator.py` (new `cmd_status()` + `_parse_accounts_arg()`), `chaoxing_cli.ps1` (status switch case)

---

### Fix 3: Comma-Separated Multi-Account Input (`0,2`)

**Before:** Only `A` (all) or single number. Entering `0,2` parsed as single account `0`.

**After:**
- Regex `^\d+,\d` detects comma input → splits into `$AccountList` array
- New `--accounts 0,2` flag in orchestrator
- `_parse_accounts_arg()` unifies `--accounts` / `--account` / `--all-accounts` parsing
- All switch cases pass `--accounts` when `$AccountList.Count -gt 1`

**Files:** `chaoxing_cli.ps1` (menu + all switch cases), `chaoxing_orchestrator.py` (argparse + dispatch)

---

### Fix 4: Return to Main Menu

**Before:** After execution, `chaoxing_cli.bat` just did `pause` + `exit`.

**After:** `:menu` loop → after "Close all browser sessions?" → "Return to main menu? [y/N]" → `goto menu`

**Files:** `chaoxing_cli.bat`

---

### Fix 5: Scan-Only Skip Confirmation Prompt

**Before:** Multi-account mode always asked `Proceed with multi-account processing? [y/N]` even for read-only scan. Prompt invisible in PowerShell pipe → hung.

**After:** `if not args.scan_only:` wraps the confirmation prompt. Also fixed prompt_text logic: uses `len(accounts_to_run)` instead of `args.account is not None`.

**Files:** `chaoxing_orchestrator.py` (multi-account dispatch confirmation gate)

---

### Fix 6: No Browser Opened (Missing Session Check)

**Before:** `ensure_logged_in()` assumed browser session existed. `pw_snapshot()` on non-existent session returned error text → nothing matched → `pw_goto()` also failed → "Cannot reach personal space".

**After:** Added `is_chaoxing_browser_open()` guard at top of `ensure_logged_in()`. No session → `chaoxing_login()` → `ensure_chaoxing_browser()` → opens Chrome → logs in.

**Files:** `chaoxing_orchestrator.py` (ensure_logged_in + imports), `utils.py` (pw() --headed filtering)

---

### Fix 7: `--headed` Warning on Snapshot

**Before:** `pw()` appended `--headed` to ALL playwright-cli commands including `snapshot` and `run-code` which don't accept it → `[pw] Warning: Unknown option: --headed`.

**After:** Whitelist approach — `--headed` only for `open|click|fill|press|goto|type|hover|select-option|check|uncheck|drag`.

**Files:** `utils.py` (pw() headed_flag logic)

---

### Fix 8: Headless Mode Not Respected

**Before:** `ensure_chaoxing_browser()` always hardcoded `--headed` in its `open` command, ignoring `CHAOXING_HEADED` env var.

**After:** Reads `CHAOXING_HEADED` env var; when `"0"` → no `--headed` → browser opens headless.

**Files:** `utils.py` (ensure_chaoxing_browser)

---

### Fix 9: Scan-Only Never Saved Discovered State

**Before:** `scan_only` block had early `return` before `save_discovered_state()` → RESULTS SUMMARY read stale files from previous runs → showed wrong (old/single-course) data.

**After:** `save_discovered_state(dynamic_courses)` called inside `scan_only` block before return. PS1 also clears old `discovered_courses*.json` before running scan.

**Files:** `chaoxing_orchestrator.py` (both multi-thread and single-thread paths), `chaoxing_cli.ps1` (scan switch case)

---

### Fix 10: RESULTS SUMMARY — Command-Aware Output

**Before:** Always showed stale Phase C batch test results + single progress state file regardless of command.

**After:** `Show-ResultsSummary -Command $Command`:
- `batch-test` → Phase C grade results
- `scan` → per-account course discovery summary from `discovered_courses_*.json`
- `solve-quiz` / `complete-content` / `full-auto` → per-account progress from `progress_state_*.json`
- `status` → skipped (has own formatted output)
- Default file (no chrome-N suffix) → maps to account `"0"`

**Files:** `chaoxing_cli.ps1` (Show-ResultsSummary rewrite)

---

## Files Modified This Session

| File | Changes |
|------|---------|
| `chaoxing_cli.ps1` | Menu restructure, status parsing, RESULTS SUMMARY rewrite, account comma input, scan cleanup |
| `chaoxing_cli.bat` | Return-to-menu loop |
| `scripts/chaoxing_orchestrator.py` | `cmd_status()`, `_parse_accounts_arg()`, `--status`/`--accounts` flags, ensure_logged_in fix, scan save fix, confirmation gate fix |
| `scripts/utils.py` | `pw()` headed whitelist, `ensure_chaoxing_browser()` headless support |

## Current Architecture (Post-Fix)

```
chaoxing_cli.bat
  └─ chaoxing_cli.ps1
       ├─ Invoke-InteractiveMenu
       │    Q1: Account scope (A / 0,2 / Enter)
       │    Q2: Headed? [Y/n] or [y/N]
       │    Q3: Course name (destructive only)
       │    Q4: Dry run? (conditional)
       │    Q5: Resume? (conditional)
       └─ Switch ($Command)
            ├─ status    → orchestrator --status → STATUS:[N] → formatted table
            ├─ scan      → orchestrator --scan-only → discovered_courses_*.json → SUMMARY
            ├─ solve-quiz→ orchestrator → progress_state_*.json → SUMMARY
            ├─ complete-content → orchestrator → SUMMARY
            ├─ full-auto → orchestrator → SUMMARY
            └─ batch-test→ Invoke-BatchTest → Phase C results → SUMMARY
```

---

### Fix 11: Credential Cache — Stop Per-Thread Re-Logging

**Before:** `read_all_chaoxing_credentials()` parsed the file fresh every call. With 3 threads each calling it 3× (from `ensure_chaoxing_browser`, `chaoxing_login`, `cmd_status`), the log showed "Loaded credentials [0][1][2]" 9 times.

**After:** Module-level `_ALL_CREDS_CACHE` — first call parses + logs, subsequent calls return cached list instantly. Total log: 1× "Loaded credentials" per unique account.

**Files:** `utils.py` (read_all_chaoxing_credentials)

---

### Fix 12: Near-Complete Threshold (95%+) 

**Before:** `scan_courses()` filtered at `percent < 100`, so 95/100 courses appeared in unfinished list even though they're effectively done.

**After:** `COMPLETION_THRESHOLD = 95` in the JS scanner. Courses at ≥95% are treated as complete and excluded from the unfinished list.

**Files:** `utils.py` (scan_courses JS)

---

### Fix 13: Course Deduplication by courseid

**Before:** Same course appearing in multiple cards (duplicate listings with different clazzids) showed up twice in the course list.

**After:** `seenIds` Set in JS scanner deduplicates by `courseid` before returning the final list.

**Files:** `utils.py` (scan_courses JS)

---

### Fix 14: Skip Section Scan for 0/0 Courses

**Before:** `discover_courses()` called `scan_course_sections()` for EVERY course including 0/0 progress ones — full navigation + 章节 click + DOM parse wasted ~10s per course.

**After:** Courses with `total == 0` get a minimal entry (`chapters: [], quiz_sections: [], content_sections: []`) without any navigation. Saves ~10s per 0/0 course.

**Files:** `chaoxing_orchestrator.py` (discover_courses)

---

### Fix 15: Progress Indicator + Compact Output

**Before:** `discover_courses()` output was verbose: `--- Scanning sections for [1/12]: XYZ ---` then per-chapter tree dump to stdout. No way to see progress at a glance.

**After:** 
- Progress counter: `[2/12] Scanning sections: course_name...`
- Compact summary: `→ 7 chapters, 0 quiz + 15 content sections`
- Full chapter tree only in log file (`logs/chaoxing_YYYYMMDD.log`)
- scan_only output reduced to one line per course with tag badges

**Files:** `chaoxing_orchestrator.py` (discover_courses + both scan_only blocks)

---

### Fix 16: Browser Window Title — Account Identifier

**Before:** All headed browser windows showed the same title, making it impossible to tell which window belonged to which account.

**After:** `ensure_chaoxing_browser()` sets `document.title = "超星 Account N"` after opening. In headed mode, window title bars clearly show which account is which.

**Files:** `utils.py` (ensure_chaoxing_browser)

---

### Fix 17: Bugfix — course_filter "Available:" Showed Empty

**Before:** `discover_courses()` filtered `course_infos` in-place, so when no match was found the `Available:` log showed `[]` (the already-empty filtered list).

**After:** Filter into `filtered` temp variable first; only overwrite `course_infos` if matches found. `Available:` now shows the actual available courses.

**Files:** `chaoxing_orchestrator.py` (discover_courses)

---

### Fix 18: PS1 Scan Summary — Percentage Display

**Before:** Scan RESULTS SUMMARY showed raw `X/Y` without percentage.

**After:** Computes and displays percentage: `58/103 (56.3%)`. Also uses `Ch×N` tag instead of `Content×N` for consistency.

**Files:** `chaoxing_cli.ps1` (Show-ResultsSummary)

---

### Fix 19: Split-Terminal UI — Progress Bars + Detail Log Terminal

**Before:** All Python stdout (login, scan, chapter trees) dumped to the main panel, mixing progress with verbose detail. No way to see per-account status at a glance.

**After:**
- **New terminal window:** Opens automatically for multi-account commands, tails `logs/chaoxing_YYYYMMDD.log` with `Get-Content -Wait`. All detailed INFO output scrolls there.
- **Main panel:** Shows only PROGRESS lines formatted as progress bars:
  ```
  ── Account Progress ──
    [→] Account  0 [####------------] 25% Scanning: 大学物理ABC（下）
    [✓] Account  1 [####################] 100% DONE — 7 courses
  ```
- **`progress()` function** in `utils.py`: Machine-parseable `PROGRESS:[N] cur/total msg` lines.
- **`Invoke-PythonScript -Progress`** switch: Filters stdout — PROGRESS → bars, ERROR/WARN → colored text, everything else → suppressed (goes to log terminal).
- Single-account commands still use normal mode (all output to main panel).

**Files:** `utils.py` (progress function), `chaoxing_orchestrator.py` (progress calls), `chaoxing_cli.ps1` (Invoke-PythonScript rewrite, -Progress switch, new terminal launch)

---

### Fix 20: Stale Browser Session Recovery

**Before:** `ensure_logged_in()` called `pw_snapshot()` on existing sessions without error handling. A dead tab (crashed renderer, stale from previous run) caused snapshot to hang → thread stuck forever → no RESULTS SUMMARY.

**After:** `try/except` around `pw_snapshot()`. Empty/broken snapshot → close stale session via `playwright-cli close` → recreate with `chaoxing_login()`. Also guards against snapshot returning < 20 chars (dead tab).

**Files:** `chaoxing_orchestrator.py` (ensure_logged_in)

---

### Fix 21: Start-Process Argument Array — Fix Parentheses-in-Path Bug

**Before:** `Start-Process powershell.exe -ArgumentList $psArg` where `$psArg` was a single string like `-NoExit -Command "...Get-Content -Path 'E:\...chaoxing.(xuexitong\logs\...'"`. PowerShell 5.1 split the string on spaces, and the `(` in `chaoxing.(xuexitong` was interpreted as expression grouping → `ParameterBindingException`.

**After:**
- Array form: `-ArgumentList @("-NoExit", "-NoProfile", "-Command", $psCmdArg)` — each argument passed separately, no splitting.
- `-LiteralPath` instead of `-Path` in `Get-Content` to avoid wildcard interpretation of `[` `]`.
- Removed embedded `(close this window...)` parenthetical from the header message.

**Files:** `chaoxing_cli.ps1` (Invoke-PythonScript progress-mode terminal launch)

---

### Fix 22: `$args` Automatic Variable Conflict

**Before:** All 5 switch cases assigned to `$args = @(...)` — `$args` is a PowerShell automatic variable (holds undeclared parameters). Reassigning it can cause unexpected parameter binding in downstream cmdlets.

**After:** Renamed to `$pyArgs` in all switch cases (`status`, `scan`, `solve-quiz`, `complete-content`, `full-auto`).

**Files:** `chaoxing_cli.ps1` (all switch cases)

---

## Files Modified (Fixes 11–22)

| File | Changes |
|------|---------|
| `scripts/utils.py` | Credential cache (`_ALL_CREDS_CACHE`), 95% completion threshold, courseid dedup, browser window title, `progress()` function |
| `scripts/chaoxing_orchestrator.py` | Skip 0/0 courses, progress counter + compact output, course_filter bugfix, stale session recovery, `progress()` calls at login/scan/complete milestones |
| `chaoxing_cli.ps1` | Scan summary %, `Invoke-PythonScript` rewrite with `-Progress` switch, new terminal launch for detail log, progress bar rendering, `$args`→`$pyArgs` rename, `Start-Process` array fix |
| `chaoxing_cli.bat` | (unchanged) |
| `FIXLOG.md` | Fixes 11–22 documented |

---

## Session: Split-Terminal UI Audit + Progress Gap Fixes — 2026-06-23

Parallel 4-agent audit of all 6 commands + orchestrator flow. Found 17 issues, fixed 11 (2 deferred: L1 batch-test multi-account, M6 label change already done).

### Fix 23: CRITICAL — `Invoke-PythonScript` MessageData Bug

**Before:** `$inProgress = $Event.MessageData` — read the entire hashtable `@{State=...; InProgress=$Progress}` as a boolean. Non-null hashtable always truthy → progress filter ALWAYS active, even for single-account mode.

**After:** `$inProgress = $Event.MessageData.InProgress` — reads the boolean property. Single-account `scan`/`full-auto` now correctly bypass the progress filter and show all output.

**Files:** `chaoxing_cli.ps1` line 290

---

### Fix 24: `solve-quiz` Missing `--all-accounts`

**Before:** Only checked `$Script:AccountList.Count -gt 1` and `$Account -ge 0`. User selecting "A" in interactive menu silently fell through to single-account default.

**After:** Added `if ($AllAccounts) { $pyArgs += "--all-accounts" }` before existing checks.

**Files:** `chaoxing_cli.ps1` solve-quiz switch case

---

### Fix 25: `complete-content` Missing `--all-accounts`

**Before:** Same bug as Fix 24 — no `$AllAccounts` branch.

**After:** Same fix — three-branch account resolution consistent with all other commands.

**Files:** `chaoxing_cli.ps1` complete-content switch case

---

### Fix 26: `solve-quiz` / `complete-content` → Split-Terminal UI

**Before:** Used raw `& $PythonCmd -u @pyArgs 2>&1` — multi-account output dumped mixed into main panel. No progress bars, no detail terminal.

**After:** Both now use `Invoke-PythonScript -ScriptName "chaoxing_orchestrator.py" -Arguments $pyArgs -Progress:$multiAccount`. Multi-account → new terminal tails log file, main panel shows progress bars. Single-account → normal passthrough.

**Files:** `chaoxing_cli.ps1` solve-quiz + complete-content switch cases

---

### Fix 27: `status` stderr Silently Discarded

**Before:** `$raw = & $PythonCmd -u @pyArgs 2>&1` merged stderr, but only `^STATUS:` regex lines were parsed. All `[ERROR]`/`[WARN]` lines silently swallowed.

**After:** After the status table, also extract and display any `[ERROR]` (red) / `[WARN]` (yellow) lines from the raw output.

**Files:** `chaoxing_cli.ps1` status switch case (after table, before `else` fallback)

---

### Fix 28: `full-auto` Stale File Cleanup

**Before:** `scan` cleared old `discovered_courses*.json` before running, but `full-auto` did not — could serve stale course lists from previous runs.

**After:** `full-auto` now clears `discovered_courses*.json` files before building `$pyArgs`, matching `scan` behavior.

**Files:** `chaoxing_cli.ps1` full-auto switch case

---

### Fix 29: Keyboard Monitor for `scan`

**Before:** `$needsMonitor` array omitted `scan` — long multi-account scans couldn't be Paused/Quit.

**After:** Added `"scan"` to `$needsMonitor`.

**Files:** `chaoxing_cli.ps1` line 850

---

### Fix 30: Progress Calls in Course Processing Loop

**Before:** `run_for_account()` non-scan-only path had ZERO `progress()` calls after `discover_courses()`. PS1 progress bar froze at last scan line for the entire quiz/content processing duration (could be tens of minutes).

**After:** Progress calls at every milestone:
- `"Processing: {name}"` before each course
- `"Completed: {name}"` after success
- `"FAILED: {name}"` on exception
- `"DONE — N courses"` at finish
- Also renamed local `progress` variable to `prog` to avoid shadowing the imported function.

**Files:** `chaoxing_orchestrator.py` run_for_account (Step 3 loop)

---

### Fix 31: Progress on "No Courses Found"

**Before:** `run_for_account()` returned without emitting progress when `dynamic_courses` was empty → progress bar stuck at last scan state.

**After:** `progress(account_index, "No courses (all complete or none found)")` before returning.

**Files:** `chaoxing_orchestrator.py` run_for_account (~line 330)

---

### Fix 32: Single-Account Dead Code Path Eliminated

**Before:** Lines 613–708 were a ~95-line near-duplicate of `run_for_account()` with ZERO progress calls and no session isolation. Only reachable when NO account flag was passed. Code duplication risk: any fix to `run_for_account()` had to be mirrored here.

**After:** Replaced entire block with a 9-line redirect:
```python
all_creds = read_all_chaoxing_credentials()
if all_creds:
    cred = all_creds[0]
    run_for_account(0, cred, args)
else:
    log("No credentials found.", "ERROR")
    sys.exit(1)
```
Single-account now consistently uses the same code path as multi-account, with full progress reporting and session isolation.

**Files:** `chaoxing_orchestrator.py` main() (~lines 626–634)

---

### Fix 33: Zombie Session Recovery — Specific Exception Handling

**Before:** `except Exception: pass` silently swallowed ALL failures (TimeoutExpired, FileNotFoundError, OSError). Zombie browser process could remain indefinitely.

**After:** Specific exception handling:
- `sp.TimeoutExpired` → logged with session name
- `FileNotFoundError` → logged as ERROR (playwright-cli.cmd missing)
- Generic `Exception` → logged with details
- All paths still fall through to `chaoxing_login()` for recovery
- `text=True` added for readable stderr in returncode check

**Files:** `chaoxing_orchestrator.py` ensure_logged_in (~lines 63–79)

---

### Fix 34 (Cosmetic): Menu Labels — solve-quiz / complete-content

**Before:** Labels implied quiz-only or content-only behavior. In reality both run full orchestrator (quiz + content phases).

**After:** 
- Menu: `"Process course quizzes (AI-powered) [+ content if present]"` / `"Process course content sections [+ quizzes if present]"`
- Help text: `"Process a course (quiz + content), starting with quizzes"` / `"Process a course (quiz + content), starting with content"`
- Switch headers: `"── Course Processing (Quiz + Content) ──"` / `"── Course Processing (Content + Quiz) ──"`

**Files:** `chaoxing_cli.ps1` param help, menu descriptions, switch headers

---

## Files Modified This Session (Fixes 23–34)

| File | Changes |
|------|---------|
| `chaoxing_cli.ps1` | C1 MessageData fix, H1/H2 --all-accounts, H3 -Progress for solve-quiz/complete-content, M1 status stderr display, M7 full-auto cleanup, L2 scan keyboard monitor, M6 label updates |
| `scripts/chaoxing_orchestrator.py` | M2/M4 progress in course loop, M3 progress on empty, M5 single-account redirect, M8 zombie session recovery |
| `FIXLOG.md` | Fixes 23–34 documented |

---

### Fix 35: CRITICAL — Duplicate Script Path in Invoke-PythonScript Calls

**Root Cause:** When `solve-quiz` and `complete-content` were migrated from direct `& $PythonCmd` to `Invoke-PythonScript` (Fix 26), the `$pyArgs` array retained the script path as its first element. `Invoke-PythonScript` already prepends the script path via `$scriptPath` (line 267), so Python received it TWICE:
```
python -u "E:\...\chaoxing_orchestrator.py" E:\...\chaoxing_orchestrator.py --scan-only
                                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                           argparse: error: unrecognized arguments
```
This caused ALL commands using `Invoke-PythonScript` (scan, solve-quiz, complete-content, full-auto) to fail with an argparse "unrecognized arguments" error.

**Before:** `$pyArgs = @("$ScriptDir\chaoxing_orchestrator.py", "--scan-only")` (etc.)

**After:** `$pyArgs = @("--scan-only")` — scan passes flags only.
`$pyArgs = @()` — solve-quiz / complete-content / full-auto start empty, flags appended.

**Files:** `chaoxing_cli.ps1` lines 919, 931, 944, 960

---

### Fix 36: Status `else` Fallback Restored

**Before (Fix 27 regression):** After inserting error-line display code, the `else` branch (raw output fallback) was accidentally attached to `if ($errorLines)` instead of `if ($statusLines)`. Result: raw output shown when no ERROR/WARN lines existed (even when STATUS table was displayed), and NOT shown when STATUS lines were missing but errors existed.

**After:** Error-line display moved INSIDE the `if ($statusLines)` block. `else` correctly pairs with `if ($statusLines)` — raw output only when no STATUS lines found.

**Files:** `chaoxing_cli.ps1` lines 898-911

---

## Files Modified (Fixes 35–36)

| File | Changes |
|------|---------|
| `chaoxing_cli.ps1` | Fix 35: Remove duplicate script path from $pyArgs (scan/solve-quiz/complete-content/full-auto). Fix 36: Restore status else→$statusLines pairing. Fix 37: Use temp .ps1 file for tail terminal to avoid parentheses-in-path Start-Process crash. |

---

### Fix 37: CRITICAL — Start-Process Parentheses-in-Path Crash in PS 5.1

**Root Cause:** The `-Progress` mode opens a terminal tailing the log file. The log file path `E:\...\chaoxing.(xuexitong\logs\chaoxing_YYYYMMDD.log` contains `(` and `)`. When embedded in a `-Command` script string and passed via `Start-Process -ArgumentList @(...)` array form, PS 5.1 failed to properly quote the argument. The `)` was interpreted as expression-grouping end, splitting the path. `chaoxing_20260623.log` became a stray positional argument → `ParameterBindingException`.

**Why Fix 21 didn't work:** Fix 21 replaced a single-string `$psArg` with array-form `-ArgumentList @("-NoExit", "-NoProfile", "-Command", $psCmdArg)`. But PS 5.1 joins array elements with spaces WITHOUT proper quoting for special characters like `(` `)`. The path's parentheses were still exposed.

**Fix:** Instead of embedding the path in a `-Command` script string, write the tail script to a temp `.ps1` file (in `$env:TEMP` — no parentheses), then launch with `-File "$tmpTail"`. The parentheses are only inside the script file content (a single-quoted string), never on the command line.

**Before:**
```powershell
$tailScript = "... -LiteralPath '$logFile' ..."   # path with ( ) embedded
$psCmdArg = "& { $tailScript }"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-Command", $psCmdArg)
```

**After:**
```powershell
$tmpTail = Join-Path $env:TEMP "chaoxing_tail_$pid.ps1"
$tailContent = @"
Write-Host '── Detail Log (close to stop) ──' -ForegroundColor Cyan
Get-Content -Wait -LiteralPath '$logFile' -Encoding UTF8 -Tail 0
"@
$tailContent | Out-File -FilePath $tmpTail -Encoding UTF8
Start-Process powershell.exe -ArgumentList "-NoExit -NoProfile -File `"$tmpTail`""
```

**Files:** `chaoxing_cli.ps1` Invoke-PythonScript (lines 247-263)

**Note (2026-06-23):** Fix 37 was PARTIALLY effective — the temp .ps1 approach correctly avoided parentheses in the Start-Process command line. However, the log-directory creation and file-touching code INSIDE the Progress block (lines 242-245) still used PS cmdlets (`Split-Path`, `Test-Path`, `New-Item`) with paths containing `(` `)`. Under PS 5.1, `New-Item -Path "chaoxing.(xuexitong\logs\..."` triggered `ParameterBindingException: A positional parameter cannot be found that accepts argument 'chaoxing_YYYYMMDD.log'`.

**Fix 37b (same day):** Replaced ALL file operations in the Progress block with .NET methods to completely bypass PS 5.1 argument parsing:
- `Split-Path` → `[System.IO.Path]::GetDirectoryName()`
- `Test-Path` / `New-Item -ItemType Directory` → `[System.IO.Directory]::Exists()` / `::CreateDirectory()`
- `Test-Path` / `New-Item -ItemType File` → `[System.IO.File]::Exists()` / `::Create().Dispose()`
- `Out-File` → `[System.IO.File]::WriteAllText()`
- `Start-Process -ArgumentList` → `[System.Diagnostics.Process]::Start()` with `ProcessStartInfo`
- `Join-Path` → `[System.IO.Path]::Combine()` (for temp path)

All paths with parentheses now flow through .NET APIs exclusively — PS 5.1 never parses them as command-line arguments.

## Current Architecture (Post-Fix 37)

```
chaoxing_cli.bat
  └─ chaoxing_cli.ps1
       ├─ Invoke-InteractiveMenu
       │    Q1: Account scope (A / 0,2 / Enter)
       │    Q2: Headed? [Y/n] or [y/N]
       │    Q3: Course name (destructive only)
       │    Q4: Dry run? (conditional)
       │    Q5: Resume? (conditional)
       └─ Switch ($Command)
            ├─ status    → orchestrator --status → STATUS:[N] → table
            │              + ERROR/WARN lines displayed (Fix 27)
            ├─ scan      → Invoke-PythonScript -Progress:$multiAccount ─┐
            ├─ solve-quiz→ Invoke-PythonScript -Progress:$multiAccount ─┤
            ├─ complete- → Invoke-PythonScript -Progress:$multiAccount ─┤
            │  content                                                   │
            ├─ full-auto → Invoke-PythonScript -Progress:$multiAccount ─┘
            │              ┌─ Main panel: PROGRESS bars only
            │              └─ New terminal: Get-Content -Wait logfile (detail)
            │              (Fix 26: solve-quiz + complete-content in split UI)
            └─ batch-test → Invoke-BatchTest (Phase C, single-account only)

All 5 account-aware commands now use consistent 3-branch resolution:
  if ($AllAccounts) → --all-accounts
  elseif ($Script:AccountList) → --accounts 0,2
  elseif ($Account -ge 0) → --account N
```

### Key Data Flow

```
Python (per thread) — Fix 30: progress() now at ALL milestones
  ├─ log()      → stdout + logs/chaoxing_YYYYMMDD.log
  └─ progress() → stdout: PROGRESS:[N] cur/total msg
       Login → Scan each course → Processing each course → Completed/FAILED → DONE

PS1 Invoke-PythonScript -Progress (Fix 23: $false path now works)
  ├─ New terminal: Start-Process powershell → Get-Content -Wait logfile
  └─ Main panel filter:
       PROGRESS:*  → progress bars [→] Account N [####----] XX% message
       [ERROR]/[WARN] → colored text
       "Multi-account"/"All threads" → shown
       everything else → suppressed (in log terminal)
  -Progress:$false (single acct) → all output passthrough (Fix 23)
```

### Course Scan Pipeline (per account)

```
scan_courses()
  ├─ Navigate to 个人空间 → click 课程
  ├─ JS DOM: find .course.learnCourse[id^="c_"] cards
  ├─ Filter: percent < 95% AND !is_ended AND total > 0
  ├─ Append: total==0 courses (0/0 progress, not ended)
  ├─ Deduplicate by courseid (seenIds Set)
  └─ Return sorted (highest % first)

discover_courses()
  ├─ For each course with total > 0:
  │    progress(N, "Scanning: name", i+1, total)
  │    scan_course_sections() → navigate + DOM chapter tree
  │    log compact: "→ 7 chapters, 0 quiz + 29 content"
  └─ For each course with total == 0:
       progress(N, "Skipping: name", i+1, total)
       Skip navigation — minimal entry
```

---

### Fix 38: orchestrator.py — Top-Level `pw_click` Import

**Before:** `pw_click` was imported locally inside `verify_course_completion()` at line 270: `from utils import pw_click`. This is inefficient and inconsistent — `pw_snapshot`, `pw_goto` etc. are all top-level imports.

**After:** `pw_click` added to the top-level `from utils import (...)` block. Local import removed.

**Files:** `scripts/chaoxing_orchestrator.py` (imports + line 270)

---

### Fix 39: orchestrator.py — Remove Redundant `import threading`

**Before:** `discover_courses()` at line 172 did `import threading as _thr` to get the current thread name for progress reporting. `threading` is already imported at the top level (line 18).

**After:** Uses `threading.current_thread().name` directly. Local import removed.

**Files:** `scripts/chaoxing_orchestrator.py` line 172

---

### Fix 40: orchestrator.py — Remove Unused `config = load_config()`

**Before:** `main()` at line 548 assigned `config = load_config()` but the variable was never referenced. `load_config()` is called inside per-account threads anyway, and `cfg()` is the module-level accessor.

**After:** Removed the dead assignment and its comment.

**Files:** `scripts/chaoxing_orchestrator.py` lines 547-548

---

### Fix 41: Interactive Mode — Show Browser Session Info

**Before:** `Show-StartupInfo` (which displays accounts, browser sessions, config, keyboard controls) was only called for non-interactive mode (`if (-not $isInteractive)`). Interactive mode users had no visibility into browser sessions.

**After:** `Show-StartupInfo` called unconditionally — both interactive and non-interactive modes now see the startup info block after the menu confirms.

**Files:** `chaoxing_cli.ps1` line ~799

---

### Fix 42: Timeout Detection — 3-Minute No-Progress Warning

**Before:** `Invoke-PythonScript` event loop had no stall detection. If Python hung (dead browser tab, infinite loop), the progress bar silently froze with no indication something was wrong.

**After:**
- `$timeoutTracker` synchronized hashtable with `LastProgress` timestamp and `Warned` flag
- Event handler updates `LastProgress` on every `PROGRESS:` line, resets `Warned`
- While loop checks every 500ms: if ≥3 minutes since last progress AND not yet warned → yellow `[⚠] No progress for N min — 可能卡住`
- Warning fires only once (until next PROGRESS line resets it)

**Files:** `chaoxing_cli.ps1` Invoke-PythonScript (event handler + while loop)

---

### Fix 43: Invoke-BatchTest — Multi-Account Support

**Before:** `Invoke-BatchTest` hardcoded `set_active_session('chaoxing-chrome')` and `config['courses'][0]` — single-account only. The account scope from the interactive menu was ignored.

**After:**
- Account resolution at function start: reads `$AllAccounts` / `$Script:AccountList` / `$Account` → `$batchAccounts` array
- Outer loop over accounts, inner loop over quiz sections (same as before)
- Session name: `chaoxing-chrome-$acctIdx` instead of hardcoded `chaoxing-chrome`
- Nav temp file: `_nav_temp_$acctIdx.py` (per-account, avoids collisions)
- Test script receives `--session $sessionName` flag
- Per-account summary after each account's batch finishes
- Combined cross-account summary at the end
- `$sync.Quit` checked in outer loop (skip remaining accounts)

**Files:** `chaoxing_cli.ps1` Invoke-BatchTest (lines 502-650), `tests/_test_phase_c.py` (added `--session` flag + `set_active_session`)

---

## Files Modified (Fixes 38–43)

| File | Changes |
|------|---------|
| `scripts/chaoxing_orchestrator.py` | Fix 38: pw_click top-level import. Fix 39: remove redundant threading import. Fix 40: remove unused config variable. |
| `chaoxing_cli.ps1` | Fix 41: Show-StartupInfo unconditional. Fix 42: 3-min timeout detection. Fix 43: Invoke-BatchTest multi-account rewrite. |
| `tests/_test_phase_c.py` | Fix 43: --session flag + set_active_session() call. |
