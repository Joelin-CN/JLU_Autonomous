---
name: find-undo-course-chaoxing
description: Find unfinished Chaoxing (超星学习通) courses after a successful login. Use when Codex needs to inspect the current 个人空间 page with playwright-cli, navigate to 课程, read the course card list, and report courses whose 任务点进度 is below 100%.
---

# Find Unfinished Chaoxing Courses

## Overview

Use `playwright-cli` from the workspace root against the existing logged-in Chaoxing browser session, usually `-s=chaoxing-chrome`. Start from the successful post-login personal space page, click `课程` in the sidebar, and list courses whose `任务点进度` is below `100%`.

This skill assumes login is already complete. If the browser is not logged in, use `sign-in-chaoxing` first.

## Required Setup

- Read and use the local `playwright-cli` skill before browser automation.
- Run commands from the workspace root.
- Prefer the existing persistent session: `playwright-cli.cmd -s=chaoxing-chrome ...`.
- Do not expose credentials. This workflow should not need credentials.

## Verified Starting State

The successful logged-in personal space observed after `sign-in-chaoxing` was:

- Page URL: `https://i.chaoxing.com/base`
- Page title: `个人空间`
- Visible login markers: sidebar with `首页`/`课程`/`笔记`/`消息` etc., school name in header, username in header dropdown

Confirm with:

```powershell
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

If the page is not `个人空间` or lacks the sidebar menu, navigate or log in before continuing.

## Workflow

1. Take a boxed snapshot of the current personal space page:

```powershell
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

2. Locate the `课程` menu item in the left sidebar and click it.

In the observed run, the ref was `e34`:

```powershell
playwright-cli.cmd -s=chaoxing-chrome click e34
```

Refs can change. Always use refs from the latest snapshot.

3. The courses page loads inside an iframe. Take a new snapshot to see the course cards:

```powershell
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

4. The page has two tabs at the top:
   - `我学的课` (Courses I'm taking — default active tab)
   - `我教的课` (Courses I teach)

Course cards are displayed in a 3-column grid. Each card contains:
   - A course cover image
   - Course title as a heading link (e.g., `大学物理ABC（下）`)
   - Teacher name in a paragraph (e.g., `罗小兵`)
   - University name (for some courses, e.g., `重庆邮电大学`)
   - Course dates in `开课时间：YYYY-MM-DD～YYYY-MM-DD` format (for some courses)
   - **Progress info**: Some cards have an overlay with `任务点进度: X/Y` and a percentage like `79%`
   - **Course status**: Ended courses have a `课程已结束` overlay on the image

5. Identify unfinished courses by looking for the progress indicators on each card:

   - Look for generic elements containing text matching `任务点进度:` — this is the task progress indicator
   - The percentage value appears nearby (e.g., `79%`, `0%`)
   - Courses WITHOUT any `任务点进度` text are likely not started / no tasks assigned
   - Courses with `课程已结束` overlay are archived past courses

6. Scroll down to see all courses (particularly the ended courses section at the bottom):

```powershell
playwright-cli.cmd -s=chaoxing-chrome run-code "async page => { const iframe = page.frames().find(f => f.url().includes('mooc2')); if (iframe) await iframe.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); return 'scrolled'; }"
```

Take another snapshot after scrolling.

7. Report courses organized by status:
   - **Unfinished (with progress < 100%)**: Courses showing explicit task progress below 100%
   - **Not started (no progress shown)**: Courses with no `任务点进度` indicator
   - **Ended/Archived**: Courses marked `课程已结束`
   - **Completed (100%)**: Courses with progress at 100% (exclude these)

## Observed Result From The Verified Run (2026-06-21)

The active semester had 16 total courses (12 active + 4 ended):

**Unfinished with progress < 100%:**
| Course | Tasks | Progress |
|---|---:|---:|
| 大学物理ABC（下） | 0/88 | 0% |
| 综合英语-2025 | 0/77 | 0% |
| 概率论与数理统计 | 79/100 | 79% |

**Not started (no progress indicator):**
| Course | Teacher |
|---|---|
| 2026年3月实验室安全教育测评 | 杜佳佳 |
| 西班牙语2 | 冯勤 |
| 工程伦理 | 杨振国 |
| 计算机体系结构与嵌入式系统原理 | 贺利军 |
| 计算机体系结构与嵌入式系统原理 | 贺利军 |
| 综合英语 | 陈有梅 |
| 大学物理ABC（上） | 罗小兵 |
| 2024年单片机竞赛基本技能比赛 | 杜佳佳 |
| C语言程序设计 | 丁晓宇 |

**Ended courses (课程已结束):**
| Course | Teacher | Date Range |
|---|---|---|
| 通用学术英语1（5期） | 刘雪琴 | 2025-02-17～2025-08-20 |
| 国家安全教育 | 庄琳璘 | — |
| 线性代数 | 张莉敏 | 2025-02-24～2025-07-31 |
| 大学英语1 | 曹洁 | 2024-09-05～2025-03-05 |

No fully completed (100%) courses were found in this account.

## Practical Notes

- The courses page is loaded inside an **iframe** (`mooc2-ans.chaoxing.com`). When using `run-code`, you need to access the iframe's content via `page.frames().find(f => f.url().includes('mooc2'))`.
- Not all courses show a `任务点进度` indicator. Courses without it may be configuration-based (no tasks assigned) or use a different evaluation method.
- There is **no pagination** on the courses page — all courses load on a single page. Scroll down to see all courses including the ended ones.
- The `课程已结束` courses appear after the active courses, separated visually.
- At the bottom there are links to `已结束课程` (archive) and `已退课课程` (dropped courses) pages for historical records.
- Refs change between sessions. Always use refs from the latest snapshot.
- The sidebar menu item for 课程 changes its accessible name after being visited (from ` 课程` to `课程菜单项已访问`).

## Failure Handling

- If `Browser 'chaoxing-chrome' is not open`, open or reattach the browser session, or run `sign-in-chaoxing`.
- If the page is on `用户登录` (login page), login is required before this skill applies.
- If the courses page does not load, check that the sidebar click registered. Try clicking again or navigating directly.
- If a captcha, SMS, or other human verification appears during re-login, stop and ask the user to complete it in the headed browser.
