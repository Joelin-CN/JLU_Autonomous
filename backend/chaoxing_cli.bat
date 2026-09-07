@echo off
REM 超星学习通自动化 — CLI 启动器
REM 绕过 PowerShell 执行策略 + 强制 UTF-8 编码
chcp 65001 >nul 2>&1
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0chaoxing_cli.ps1" %*
