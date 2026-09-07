<#
.SYNOPSIS
    超星学习通自动化 CLI — Unified entry point
.DESCRIPTION
    Interactive menu + command dispatch + keyboard monitor.
    6 modes: status, scan, solve-quiz, complete-content, full-auto, batch-test
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "scan", "solve-quiz", "complete-content", "full-auto", "batch-test")]
    [string]$Command,

    [string]$Course,
    [string]$Section,
    [string]$From,
    [int]$Account = -1,
    [switch]$AllAccounts,
    [switch]$Headed,
    [switch]$DryRun,
    [switch]$Resume,
    [switch]$ScanOnly,
    [switch]$QuizOnly,
    [switch]$ContentOnly,
    [switch]$Yes
)

# ── Path Setup ──────────────────────────────────────────────────
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:CHAOXING_WORKSPACE = $ScriptRoot
$env:CHAOXING_DATA_DIR = Join-Path (Split-Path $ScriptRoot -Parent) "data"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# Interpreter resolution: CHAOXING_PYTHON env > conda env chaoxing-backend
# (has volcengine-python-sdk for the balance query) > python on PATH.
function Resolve-PythonExe {
    if ($env:CHAOXING_PYTHON -and (Test-Path $env:CHAOXING_PYTHON)) { return $env:CHAOXING_PYTHON }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    Write-Host "  [ERROR] 未找到 Python。请安装 Python 3.10+，或设置 CHAOXING_PYTHON 环境变量指向解释器。" -ForegroundColor Red
    exit 1
}

# ── Banner ──────────────────────────────────────────────────────
function Show-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║      超星学习通自动化 — Chaoxing Auto-Course      ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# ── Interactive Menu ────────────────────────────────────────────
function Show-Menu {
    Write-Host "  命令列表:" -ForegroundColor Yellow
    Write-Host "    [1] status             查看课程状态和进度"
    Write-Host "    [2] scan               扫描课程和章节结构"
    Write-Host "    [3] solve-quiz         解答章节测试 (AI驱动)"
    Write-Host "    [4] complete-content   完成视频/文档/音频内容"
    Write-Host "    [5] full-auto          全自动处理 (答题+内容)"
    Write-Host "    [6] batch-test         批量测试 (Phase C 验证)"
    Write-Host "    [Q] 退出"
    Write-Host ""
    Write-Host "  执行过程中: P = 暂停/继续   Q = 优雅停止"
    Write-Host ""
}

# ── Environment Setup ───────────────────────────────────────────
function Set-HeadedMode {
    if ($Headed) {
        $env:CHAOXING_HEADED = "1"
        Write-Host "  [浏览器] 可见模式" -ForegroundColor DarkYellow
    } else {
        $env:CHAOXING_HEADED = "0"
    }
}

# ── Build Python Arguments ──────────────────────────────────────
function Build-PythonArgs {
    param([string]$CommandName, [string]$ExtraArgs = "")
    $args = @()

    # Route command to appropriate Python script
    switch ($CommandName) {
        "status" {
            $script:PythonScript = "scripts/chaoxing_orchestrator.py"
            $args += "--status"
        }
        "scan" {
            $script:PythonScript = "scripts/chaoxing_orchestrator.py"
            $args += "--scan-only"
        }
        "solve-quiz" {
            $script:PythonScript = "scripts/chaoxing_orchestrator.py"
            $args += "--quiz-only"
        }
        "complete-content" {
            $script:PythonScript = "scripts/chaoxing_orchestrator.py"
            $args += "--content-only"
        }
        "full-auto" {
            $script:PythonScript = "scripts/chaoxing_orchestrator.py"
        }
        "batch-test" {
            $script:PythonScript = "tests/_test_phase_c.py"
            if ($From) { $args += "--section", $From }
        }
    }

    if ($Course) { $args += "--course", $Course }
    if ($DryRun) { $args += "--dry-run" }
    if ($Resume) { $args += "--resume" }
    if ($AllAccounts) { $args += "--all-accounts" }
    if ($Account -ge 0) { $args += "--account", $Account }
    if ($Yes) { $args += "--yes" }

    return $args
}

# ── Invoke Python Script ────────────────────────────────────────
function Invoke-PythonScript {
    param(
        [string]$ScriptName,
        [string[]]$Arguments,
        [switch]$WithProgress
    )

    $scriptPath = Join-Path $ScriptRoot $ScriptName
    if (-not (Test-Path $scriptPath)) {
        Write-Host "  [ERROR] Script not found: $scriptPath" -ForegroundColor Red
        return $false
    }

    $procInfo = New-Object System.Diagnostics.ProcessStartInfo
    $procInfo.FileName = Resolve-PythonExe
    $procInfo.Arguments = "`"$scriptPath`" $($Arguments -join ' ')"
    $procInfo.UseShellExecute = $false
    $procInfo.RedirectStandardOutput = $true
    $procInfo.RedirectStandardError = $true
    $procInfo.RedirectStandardInput = $true
    $procInfo.CreateNoWindow = $true
    $procInfo.WorkingDirectory = $ScriptRoot

    # Set UTF-8 environment
    $procInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $procInfo.EnvironmentVariables["PYTHONUTF8"] = "1"

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $procInfo

    # Register output handlers
    $outputBuilder = New-Object System.Text.StringBuilder
    $lastProgressTime = Get-Date

    $outputEvent = Register-ObjectEvent -InputObject $proc `
        -EventName 'OutputDataReceived' `
        -Action {
            $line = $EventArgs.Data
            if ($line -match '^PROGRESS:') {
                # Parse progress lines for progress bar rendering
                $progressLine = $line -replace '^PROGRESS:', ''
                Write-Host "`r  $progressLine" -NoNewline -ForegroundColor Cyan
                $Event.MessageData.LastProgressTime = Get-Date
            } elseif ($line) {
                Write-Host $line
                $null = $Event.MessageData.OutputBuilder.AppendLine($line)
            }
        } -MessageData @{ OutputBuilder = $outputBuilder; LastProgressTime = $lastProgressTime }

    $errorEvent = Register-ObjectEvent -InputObject $proc `
        -EventName 'ErrorDataReceived' `
        -Action {
            $line = $EventArgs.Data
            if ($line) {
                Write-Host "  [stderr] $line" -ForegroundColor DarkYellow
                $null = $Event.MessageData.OutputBuilder.AppendLine("[stderr] $line")
            }
        } -MessageData @{ OutputBuilder = $outputBuilder }

    try {
        $proc.Start() | Out-Null
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()

        # Wait with progress timeout detection
        $exitTimeout = 1800  # 30 min max
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $paused = $false
        $quitRequested = $false
        while (-not $proc.HasExited) {
            $proc.WaitForExit(3000) | Out-Null

            # Live keyboard control: P toggles pause/resume, Q requests stop.
            if (-not $proc.HasExited -and [Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq 'P') {
                    if ($paused) {
                        $proc.StandardInput.WriteLine("RESUME")
                        $paused = $false
                        Write-Host "`n  ▶ 继续执行" -ForegroundColor Green
                    } else {
                        $proc.StandardInput.WriteLine("PAUSE")
                        $paused = $true
                        Write-Host "`n  ⏸ 已暂停 — 按 P 继续" -ForegroundColor Yellow
                    }
                } elseif ($key.Key -eq 'Q') {
                    $proc.StandardInput.WriteLine("STOP")
                    $quitRequested = $true
                    Write-Host "`n  ⏹ 停止信号已发送 — 等待当前步骤完成..." -ForegroundColor Red
                }
            }

            if ($quitRequested -and $proc.WaitForExit(30000)) {
                break
            }

            if ($sw.Elapsed.TotalSeconds -gt $exitTimeout) {
                Write-Host "`n  [TIMEOUT] Process exceeded ${exitTimeout}s limit — terminating." -ForegroundColor Red
                $proc.Kill()
                break
            }
        }

        try { $proc.StandardInput.Close() } catch {}
        $proc.WaitForExit(5000) | Out-Null
        $exitCode = $proc.ExitCode
        Write-Host ""
        return $exitCode -eq 0
    }
    finally {
        Unregister-Event -SourceIdentifier $outputEvent.Name -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $errorEvent.Name -ErrorAction SilentlyContinue
        $proc.Dispose()
    }
}

# ── Main ────────────────────────────────────────────────────────
function Main {
    Show-Banner

    # Direct command-line mode
    if ($Command) {
        Set-HeadedMode
        $pyArgs = Build-PythonArgs $Command
        Write-Host "  执行: $Command" -ForegroundColor Green
        Write-Host "  脚本: $PythonScript" -ForegroundColor DarkGray
        Write-Host "  参数: $($pyArgs -join ' ')" -ForegroundColor DarkGray
        Write-Host ""
        $result = Invoke-PythonScript -ScriptName $PythonScript -Arguments $pyArgs -WithProgress
        if ($result) { Write-Host "  ✓ 命令执行完成" -ForegroundColor Green }
        else { Write-Host "  ✗ 命令执行失败 (exit code: $LASTEXITCODE)" -ForegroundColor Red }
        return
    }

    # Interactive menu loop
    while ($true) {
        Show-Menu
        $choice = Read-Host "  请选择命令 [1-6/K/Q]"

        switch ($choice.ToUpper()) {
            'Q' {
                Write-Host "  再见!" -ForegroundColor Green
                return
            }
            { $_ -in @('1','2','3','4','5','6') } {
                $cmdMap = @{
                    '1' = 'status'
                    '2' = 'scan'
                    '3' = 'solve-quiz'
                    '4' = 'complete-content'
                    '5' = 'full-auto'
                    '6' = 'batch-test'
                }
                $cmd = $cmdMap[$choice]

                # Account selection
                Write-Host ""
                $acctChoice = Read-Host "  账号范围 [A=全部 / 0,2=指定 / Enter=默认账号0]"
                if ($acctChoice -eq 'A' -or $acctChoice -eq 'a') {
                    $script:AllAccounts = $true
                    $script:Account = -1
                } elseif ($acctChoice -match '^\d+(,\d+)*$') {
                    $script:AllAccounts = $false
                    $script:Account = [int]($acctChoice -split ',')[0]
                } else {
                    $script:AllAccounts = $false
                    $script:Account = 0
                }

                # Headed mode
                $headedChoice = Read-Host "  浏览器可见? [y/N]"
                $script:Headed = ($headedChoice -eq 'y' -or $headedChoice -eq 'Y')

                # Course filter (optional)
                $courseFilter = Read-Host "  课程筛选 (Enter=全部未完成)"
                if ($courseFilter) { $script:Course = $courseFilter }
                else { $script:Course = $null }

                # Destructive commands: dry-run / resume options
                if ($cmd -in @('solve-quiz', 'complete-content', 'full-auto')) {
                    Write-Host ""
                    Write-Host "  执行选项:" -ForegroundColor Yellow
                    Write-Host "    [Enter]  正常执行 (提交答案)"
                    Write-Host "    [D]      Dry Run (预览, 不提交)"
                    Write-Host "    [R]      Resume (断点续传)"
                    $execChoice = Read-Host "  请选择"
                    switch ($execChoice.ToUpper()) {
                        'D' { $script:DryRun = $true; $script:Resume = $false }
                        'R' { $script:DryRun = $false; $script:Resume = $true }
                        default { $script:DryRun = $false; $script:Resume = $false }
                    }
                }

                # Batch-test: starting section
                if ($cmd -eq 'batch-test') {
                    $fromSection = Read-Host "  起始章节 (Enter=全部)"
                    if ($fromSection) { $script:From = $fromSection }
                    else { $script:From = $null }
                }

                # Confirm
                Write-Host ""
                Write-Host "  ─── 确认 ───" -ForegroundColor Yellow
                Write-Host "  命令:     $cmd" -ForegroundColor White
                Write-Host "  账号:     $(if ($AllAccounts) {'全部'} else {$Account})" -ForegroundColor White
                Write-Host "  浏览器:   $(if ($Headed) {'可见'} else {'隐藏'})" -ForegroundColor White
                if ($Course) { Write-Host "  课程:     $Course" -ForegroundColor White }
                if ($DryRun) { Write-Host "  模式:     DRY RUN (预览)" -ForegroundColor Magenta }
                if ($Resume) { Write-Host "  模式:     RESUME (断点续传)" -ForegroundColor Magenta }
                Write-Host ""

                $confirm = Read-Host "  确认执行? [Y/n]"
                if ($confirm -eq 'n' -or $confirm -eq 'N') {
                    Write-Host "  已取消。" -ForegroundColor DarkGray
                    continue
                }

                # Execute
                Set-HeadedMode
                $pyArgs = Build-PythonArgs $cmd
                Write-Host ""
                Write-Host "  执行中..." -ForegroundColor Green
                Write-Host ""

                $result = Invoke-PythonScript -ScriptName $PythonScript -Arguments $pyArgs -WithProgress

                Write-Host ""
                if ($result) { Write-Host "  ✓ 命令执行完成" -ForegroundColor Green }
                else { Write-Host "  ✗ 命令执行失败" -ForegroundColor Red }
                Write-Host ""

                # Loop back
                $again = Read-Host "  继续执行其他命令? [Y/n]"
                if ($again -eq 'n' -or $again -eq 'N') {
                    Write-Host "  再见!" -ForegroundColor Green
                    return
                }
                Write-Host ""
            }
            default {
                Write-Host "  无效选择，请重新输入。" -ForegroundColor Red
            }
        }
    }
}

# ── Entry Point ─────────────────────────────────────────────────
Main
