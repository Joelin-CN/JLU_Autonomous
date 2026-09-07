---
name: find-undo-course
description: Find unfinished OUCHN portal courses after a successful login. Use when Codex needs to inspect the current 国家开放大学融合门户 page with playwright-cli, read the 我的课程 list, handle pagination, and report courses whose 学习进度 is below 100%.
---

# Find Unfinished OUCHN Courses

## Overview

Use `playwright-cli` from the workspace root against the existing logged-in OUCHN browser session, usually `-s=ouchn-chrome`. Start from the successful post-login portal page and list courses in `我的课程` whose `学习进度` is not `100%`.

This skill assumes login is already complete. If the browser is not logged in, use `sign-in-ouchn` first.

## Required Setup

- Read and use the local `playwright-cli` skill before browser automation.
- Run commands from the workspace root.
- Prefer the existing persistent session: `playwright-cli.cmd -s=ouchn-chrome ...`.
- Do not expose credentials. This workflow should not need credentials.

## Verified Starting State

The successful logged-in portal state observed after `sign-in-ouchn` was:

- Page URL: `https://menhu.pt.ouchn.cn/site/ouchnPc/index`
- Page title: `首页 - 国家开放大学融合门户`
- Visible login markers: `退出登录`, `我的课程`, `系统直通车`, `办事服务`

Confirm with:

```powershell
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

If the page is not the portal or lacks `我的课程`, navigate or log in before continuing.

## Workflow

1. Take a boxed snapshot of the current portal page:

```powershell
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

2. Locate the `我的课程` section and read each course card on the active page.

Each course card contains:

- Course title in a paragraph, for example `计算机应用基础`
- Course metadata such as `课程代码`, `课程状态`, and `开课时间`
- A `学习进度：` row with a percent value inside a progressbar
- A `去学习` link

3. Record only courses whose progress is below `100%`.

4. Check pagination at the bottom of `我的课程`.

Observed controls:

- `共 7 条`
- Page list items like `第 1 页`, `第 2 页`
- `上一页` / `下一页`
- Current page number in the `前往 ... 页` spinbutton

If another page exists, click it using the latest snapshot ref. In the observed run, the second page ref was `e338`:

```powershell
playwright-cli.cmd -s=ouchn-chrome click e338
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

Refs can change. Always use refs from the latest snapshot.

5. Combine results from all pages and report course names with progress values.

## Observed Result From The Verified Run

The current term had `共 7 条` courses. Six were below `100%`:

| Course | Progress |
|---|---:|
| 计算机应用基础 | 49.6% |
| 社会心理适应 | 83.1% |
| 毛泽东思想和中国特色社会主义理论体系概论 | 38.8% |
| 临床医学概论 | 25.8% |
| 形势与政策 | 51.1% |
| 常见疾病与预防 | 89% |

`职业道德与药学伦理` was `100%`, so it was excluded.

## Practical Notes

- Do not assume all courses are on the first page. The observed page showed six cards on page 1 and one card on page 2.
- The first page included one complete course at `100%`; filter it out.
- A first attempt to use `run-code` with Chinese text failed because PowerShell quoting caused `text=我的课程` to be evaluated incorrectly, resulting in `ReferenceError: 我的课程 is not defined`.
- Prefer `snapshot --boxes` and ref-based pagination for this portal. If using `run-code`, use PowerShell-safe quoting or `--filename` with a file that contains one function expression such as `async page => { ... }`.
- After clicking a pagination control, take a fresh snapshot before reading refs or content.

## Failure Handling

- If `Browser 'ouchn-chrome' is not open`, open or reattach the browser session, or run `sign-in-ouchn`.
- If the page is on `统一身份认证平台`, login is required before this skill applies.
- If no pagination is visible, report the courses found on the current page and state that no additional pages were visible.
- If a captcha, SMS, or other human verification appears during re-login, stop and ask the user to complete it in the headed browser.
