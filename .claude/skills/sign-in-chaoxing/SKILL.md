---
name: sign-in-chaoxing
description: Automate signing in to the Chaoxing (超星学习通) passport/login page with playwright-cli using credentials stored in passwords/pwd.txt. Use when Codex needs to open passport2.chaoxing.com or i.chaoxing.com, fill the Chaoxing account/password login form, click login, and verify the resulting landing page.
---

# Sign In Chaoxing (超星学习通)

## Overview

Use `playwright-cli` from the workspace root to open the Chaoxing login URL in a headed persistent Chrome session, read the matching local credentials from `passwords/pwd.txt`, submit the login form, and confirm the landing page.

Do not expose stored credentials in chat. Read them only to fill the form.

## Required Setup

- Use the local `playwright-cli` skill before browser automation.
- Run commands from the workspace root.
- Prefer a named persistent session such as `-s=chaoxing` or `-s=chaoxing-chrome`.
- Default to Chrome with `--browser=chrome` unless the user explicitly asks for another browser.
- On Windows, pass the login URL with PowerShell `--%` because the URL contains `&` query separators.
- If `playwright-cli` needs to write its daemon/profile files under the user directory and sandboxing blocks it, rerun the same command with escalation.

## Credential Lookup

Read `passwords/pwd.txt` and find the block whose website contains:

- `passport2.chaoxing.com`
- `i.chaoxing.com`
- `chaoxing.com`

The observed block format was:

```text
{
    网站:<Chaoxing login URL>
    账号:<account>
    密码:<password>
}
```

Use the values after `账号:` and `密码:`. Do not print the password or include it in summaries.

## Workflow

1. Open the login URL:

```powershell
playwright-cli.cmd -s=chaoxing-chrome --% open --browser=chrome --headed --persistent "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com"
```

2. Take a boxed snapshot:

```powershell
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

3. If the page title is `用户登录`, fill the account/password form.

Observed login page text and controls:

- Page URL starts with `https://passport2.chaoxing.com/login`
- Page title: `用户登录`
- Heading: `用户登录`
- Account textbox placeholder/name: `手机号/超星号` (ref: `e10` in the observed run)
- Password textbox placeholder/name: `学习通密码` (ref: `e13` in the observed run)
- Login button: `登录` (ref: `e18` in the observed run)
- Alternative login tab: `验证码登录` (SMS verification code login)
- Register link: `新用户注册`
- Auto-login checkbox: `下次自动登录`
- Forgot password link: `忘记密码？`
- QR code login panel on the right side: `使用学习通APP扫码登录`
- Agreement text: `我已阅读并同意学习通《隐私政策》和《用户协议》`
- Footer text: `Copyright © 2026 北京世纪超星信息技术发展有限责任公司`

4. Do NOT use `playwright-cli fill` as it echoes the password in generated code output. Use clipboard paste instead:

```powershell
# Set account in clipboard, click account field, paste
$null = Set-Clipboard "<account>"; playwright-cli.cmd -s=chaoxing-chrome click e10; playwright-cli.cmd -s=chaoxing-chrome press Control+V

# Set password in clipboard, click password field, paste
$null = Set-Clipboard "<password>"; playwright-cli.cmd -s=chaoxing-chrome click e13; playwright-cli.cmd -s=chaoxing-chrome press Control+V
```

5. Click `登录` and wait for navigation:

```powershell
playwright-cli.cmd -s=chaoxing-chrome click e18
```

6. Confirm success with another snapshot. The observed successful state was:

- Page URL: `https://i.chaoxing.com/base`
- Page title: `个人空间`
- Header: `重庆邮电大学(学生)` (school name — will vary by user)
- User dropdown: `账号：林琦沅` (username — will vary by user)
- Header links: `输入邀请码`
- Sidebar menu items: `首页`, `常用`, `应用中心`, `课程`, `笔记`, `消息`, `小组`, `云盘`, `通讯录`, `收件箱`
- Main content area shows a weekly course schedule (iframe) with semester info: `2025-2026 第2学期`, week indicator: `第21周`
- Course timetable grid with 12 periods/day, Monday through Sunday
- Bottom floating links: `PC客户端下载`, `直播客户端下载`

## Verification And Human Checks

After login, check for a landing page at `i.chaoxing.com/base` with title `个人空间`. Look for the sidebar menu (首页/课程/笔记 etc.) and the school name in the header.

If the page remains on `用户登录`, inspect the snapshot for validation messages, incorrect credentials, or interactive verification.

If a captcha, slider, SMS verification, or other human verification appears, stop and ask the user to complete it in the headed browser. Do not use another AI service to solve or bypass human verification.

## Test Result (2026-06-21)

The Chrome flow was verified with session `chaoxing-chrome`:

- Initial page: `https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com`
- Initial title: `用户登录`
- Login form elements identified: account textbox `e10`, password textbox `e13`, login button `e18`
- After filling credentials via clipboard paste and clicking `登录`, the page navigated to `https://i.chaoxing.com/base`
- Final title: `个人空间`
- Visible login-state markers included the sidebar menu (首页/课程/笔记/消息 etc.), school name `重庆邮电大学(学生)`, username `林琦沅`, and a weekly course schedule
- No captcha, slider, SMS, or other interactive verification appeared during the test

## Practical Notes From The Observed Run

- Ref-based form actions that succeeded:
```powershell
$null = Set-Clipboard "<account>"; playwright-cli.cmd -s=chaoxing-chrome click e10; playwright-cli.cmd -s=chaoxing-chrome press Control+V
$null = Set-Clipboard "<password>"; playwright-cli.cmd -s=chaoxing-chrome click e13; playwright-cli.cmd -s=chaoxing-chrome press Control+V
playwright-cli.cmd -s=chaoxing-chrome click e18
```

- Refs can change between sessions. Always use refs from the latest snapshot.
- The Chaoxing login page does not require accepting a privacy agreement checkbox before login — the agreement text is passive.
- The page has a two-tab layout: `账号密码登录` (password login, the default) and `验证码登录` (SMS code login). The default tab is password login.
- A QR code panel on the right offers `使用学习通APP扫码登录` (scan QR to login via the app).
- No sandbox errors were encountered with Chrome in this run.
- A minimal `run-code` sanity check works:
```powershell
playwright-cli.cmd -s=chaoxing-chrome run-code "async page => await page.title()"
```
