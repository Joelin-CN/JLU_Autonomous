---
name: sign-in-ouchn
description: Automate signing in to the OUCHN unified identity and portal pages with playwright-cli using credentials stored in passwords/pwd.txt. Use when Codex needs to open iam.pt.ouchn.cn or menhu.pt.ouchn.cn, fill the OUCHN account/password login form, accept the privacy agreement, click login, and verify the resulting portal page.
---

# Sign In OUCHN

## Overview

Use `playwright-cli` from the workspace root to open the OUCHN identity URL in a headed persistent Chrome session, read the matching local credentials from `passwords/pwd.txt`, submit the login form, and confirm the portal landing page.

Do not expose stored credentials in chat. Read them only to fill the form.

## Required Setup

- Use the local `playwright-cli` skill before browser automation.
- Run commands from the workspace root.
- Prefer a named persistent session such as `-s=ouchn` or `-s=ouchn-chrome`.
- Default to Chrome with `--browser=chrome` unless the user explicitly asks for another browser.
- On Windows, pass the OAuth URL with PowerShell `--%` because the URL contains `&` query separators.
- If `playwright-cli` needs to write its daemon/profile files under the user directory and sandboxing blocks it, rerun the same command with escalation.

## Credential Lookup

Read `passwords/pwd.txt` and find the block whose website contains either:

- `https://iam.pt.ouchn.cn/am/oauth2/authorize`
- `https://menhu.pt.ouchn.cn`
- `pt.ouchn.cn`

The observed block format was:

```text
{
    网站:<full OUCHN OAuth URL>
    账号:<account>
    密码:<password>
}
```

Use the values after `账号:` and `密码:`. Do not print the password or include it in summaries.

## Workflow

1. Open the login URL:

```powershell
playwright-cli.cmd -s=ouchn-chrome --% open --browser=chrome --headed --persistent "https://iam.pt.ouchn.cn/am/oauth2/authorize?service=initService&response_type=code&client_id=e5d983bbfc474ea8&scope=all&decision=Allow&redirect_uri=https://menhu.pt.ouchn.cn/wap/auth/callback"
```

2. Take a boxed snapshot:

```powershell
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

3. If the page title is `统一身份认证平台`, fill the account/password form.

Observed login page text and controls:

- Page URL starts with `https://iam.pt.ouchn.cn/am/oauth2/authorize`
- Page title: `统一身份认证平台`
- Login tab/title: `账号密码登录`
- Account textbox placeholder/name: `请输入登录名`
- Password textbox placeholder/name: `请输入登录密码`
- Login button: `登 录`
- WeChat button: `微信登录`
- Agreement text: `请阅读并同意`
- Agreement links: `《教师隐私服务协议》`, `《学生隐私服务协议》`
- Footer text included `国家开放大学 版权所有`, `服务热线：400-867-9660`, and `服务邮箱：ouc-online@ouchn.edu.cn`

4. Accept the agreement before submitting. In the observed page the checkbox locator appeared as `#agreeCheckBox`, with snapshot text under `请阅读并同意`.

5. Click `登 录` and wait for navigation.

6. Confirm success with another snapshot. The observed successful state was:

- Page URL: `https://menhu.pt.ouchn.cn/site/ouchnPc/index`
- Page title: `首页 - 国家开放大学融合门户`
- Header links: `问卷调查`, `我的消息`, `操作手册`, `版本更新 NEW`
- User panel with `个人信息` and `退出登录`
- Portal sections such as `系统直通车`, `办事服务`, `我的待办`, `我的申请`
- Course section: `我的课程`
- Common app links: `学习网`, `终身教育平台`, `国家智教平台`, `数字图书馆`, `考试(学生端)`, `办事大厅`

## Practical Notes From The Observed Run

- `playwright-cli.cmd -s=ouchn list` first reported `(no browsers)` before the browser was opened.
- The first Edge open hit a sandbox error writing a Playwright daemon file under `C:\Users\Joelin\AppData\Local\ms-playwright\daemon\...`; rerunning with escalation opened the headed persistent Edge session.
- A later Chrome test hit the same sandbox error writing `ouchn-chrome.err` under the Playwright daemon directory. Rerunning the same `playwright-cli.cmd -s=ouchn-chrome --% open --browser=chrome --headed --persistent ...` command with escalation opened Chrome successfully.
- `snapshot` worked reliably for checking refs and page state.
- Combining credential parsing and several `playwright-cli` subcommands in one PowerShell script caused intermittent `Browser 'ouchn' is not open` errors, even though `snapshot` showed the session was open. Prefer single interaction commands or test `run-code` independently before batching.
- A minimal `run-code` sanity check worked:

```powershell
playwright-cli.cmd -s=ouchn run-code "async page => await page.title()"
```

- `run-code --filename` requires the file to contain one function expression, such as `async page => { ... }`. CommonJS files with `const`, `require`, or `module.exports` at top level fail with `SyntaxError: Unexpected token 'const'` because the CLI wraps the file content in parentheses and evaluates it.
- Avoid `playwright-cli fill <ref> "<password>"` when command output is visible, because the CLI echoes the generated Playwright code and can expose the password. Safer approaches are:
  - Put the value in the system clipboard with PowerShell `Set-Clipboard`, focus the textbox, then run `playwright-cli.cmd -s=ouchn-chrome press Control+V`.
  - Or use a valid `run-code` function expression that reads the local credentials and does not return them.
- The Chrome test used clipboard paste successfully: click the account field, set the account in the clipboard, press `Control+V`; click the password field, set the password in the clipboard, press `Control+V`.
- Ref-based form actions that succeeded in the observed run were:

```powershell
playwright-cli.cmd -s=ouchn-chrome click e16
playwright-cli.cmd -s=ouchn-chrome press Control+V
playwright-cli.cmd -s=ouchn-chrome click e19
playwright-cli.cmd -s=ouchn-chrome press Control+V
playwright-cli.cmd -s=ouchn-chrome check e26
playwright-cli.cmd -s=ouchn-chrome click e20
```

Refs can change. Always use refs from the latest snapshot.

## Chrome Test Result

The Chrome flow was verified with session `ouchn-chrome`:

- Initial page: `https://iam.pt.ouchn.cn/am/oauth2/authorize...`
- Initial title: `统一身份认证平台`
- After filling credentials, accepting the agreement, and clicking `登 录`, the page navigated to `https://menhu.pt.ouchn.cn/site/ouchnPc/index`.
- Final title: `首页 - 国家开放大学融合门户`
- Visible login-state markers included `退出登录`, `我的课程`, `系统直通车`, `办事服务`, and course list entries.
- No captcha, slider, SMS, or other interactive verification appeared during the Chrome test.

## Verification And Human Checks

After login, check for a portal URL and visible `退出登录`. If the page remains on `统一身份认证平台`, inspect the snapshot for validation messages, incorrect credentials, required agreement, or interactive verification.

If a captcha, slider, SMS verification, or other human verification appears, stop and ask the user to complete it in the headed browser. Do not use another AI service to solve or bypass human verification.
