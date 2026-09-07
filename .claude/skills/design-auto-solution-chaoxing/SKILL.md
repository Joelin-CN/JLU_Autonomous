---
name: design-auto-solution-chaoxing
description: Design an automation solution for completing unfinished Chaoxing (超星学习通) courses. Use when Codex has found unfinished courses via find-undo-course-chaoxing and needs to analyze course page structures, classify task types, identify special cases, and design a concrete automation script strategy before writing any code.
---

# Design Auto Solution for Chaoxing Course Completion

## Overview

After `sign-in-chaoxing` and `find-undo-course-chaoxing` have identified courses with progress below 100%, this skill guides the systematic analysis of every unfinished course's internal page structure. The goal is to produce a complete task-type classification and an automation strategy matrix before writing a single line of automation script.

**Critical principle**: Do NOT assume all courses have the same structure. Each course must be opened and its 章节 (Chapters), 作业 (Assignments), 考试 (Exams), and 讨论 (Discussions) tabs must be inspected individually. Hidden task subtypes and varying configurations can drastically change the automation approach.

## Chaoxing vs OUCHN Platform Differences

| Concept | OUCHN (国开) | Chaoxing (超星) |
|---------|-------------|-----------------|
| Main content | 全部 tab with video/pages/discussions | 章节 tab with hierarchical sections |
| Formative assessment | 形考任务 tab (tests + assignments) | 章节测试 embedded in 章节 + 作业 tab |
| Summative assessment | 终考任务 tab | 考试 tab |
| Progress metric | 学习进度: XX% | 已完成任务点: X/Y |
| Course entry | Portal card → 去学习 | Course card → course page URL |
| Page structure | Direct page navigation | SPA with sidebar + iframe |
| Content types | 音视频/参考资料/页面/讨论 | Video pages + document pages + inline quizzes |

## Required Setup

- `sign-in-chaoxing` must have completed successfully (persistent session `-s=chaoxing-chrome` is open and logged in).
- `find-undo-course-chaoxing` must have produced a list of courses with progress < 100% (任务点进度 below 100% or no progress).
- Use `playwright-cli` from the workspace root for all browser interactions.
- Run commands from the workspace root. Single `playwright-cli.cmd` actions per shell command.

## Workflow

### Phase 1: Course Inventory from Personal Space

1. From the personal space (`https://i.chaoxing.com/base`), click 课程 in the sidebar:

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <课程-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

2. For each course card in the `我学的课` grid, record:
   - Course name (e.g., `概率论与数理统计`)
   - Teacher name (e.g., `鲜思东`)
   - University (e.g., `重庆邮电大学`)
   - 任务点进度: X/Y and Z% (if shown) — courses without this have no task points assigned
   - Course URL (`https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=...&clazzid=...`)
   - `课程已结束` status (ended courses appear after active ones)

3. There is **no pagination** — all courses load on one page. Scroll down to see ended courses:

```powershell
playwright-cli.cmd -s=chaoxing-chrome run-code "async page => { const iframe = page.frames().find(f => f.url().includes('mooc2')); if (iframe) await iframe.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); return 'scrolled'; }"
```

4. Build the initial course inventory. Filter: exclude courses at 100% 任务点进度, note courses with no progress indicator, and separate ended courses.

### Phase 2: Per-Course Deep Analysis

For **every** unfinished course, navigate to its course page and inspect ALL tabs.

Open the course in the current tab:

```powershell
playwright-cli.cmd -s=chaoxing-chrome --% goto "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=<id>&clazzid=<id>&cpi=<id>&ismooc2=1&v=2"
```

The page redirects to `mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu?...`. Take a snapshot:

```powershell
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

The left sidebar has these navigation tabs:

| Tab | Chinese | Description | Snapshot Ref Pattern |
|-----|---------|-------------|---------------------|
| 课程门户 | Course Portal | Cover image, course info | `课程门户 链接` |
| AI助教 | AI Assistant | AI-powered Q&A | `AI助教` |
| 任务 | Tasks | Aggregated task view | `任务` |
| 章节 | Chapters | **Main content** — videos, pages, quizzes | `章节` |
| 讨论 | Discussions | Forum discussions | `讨论` |
| 作业 | Assignments | Standalone homework | `作业` |
| 考试 | Exams | Formal exams with constraints | `考试` |
| 资料 | Materials | Course resources/files | `资料` |
| 错题集 | Wrong Answers | Review incorrect answers | `错题集` |
| 学习记录 | Study Record | Study history/log | `学习记录` |

#### 2a. The "任务" (Tasks) Tab

Click and snapshot. May show `暂无任务` (no tasks) or a list of pending items:

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <任务-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

If empty, skip. If items exist, they're aggregated task requirements across all sections.

#### 2b. The "章节" (Chapters) Tab — MAIN CONTENT

This is **the most important tab**. Click and take a snapshot:

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <章节-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

The header shows: **`已完成任务点: X/Y`** — this is the progress counter.

The directory tree has expandable chapters. Each section has one of these types:

| Section Type | Snapshot Signature | Badge | Automation Strategy |
|---|---|---|---|
| **Content Section** | Numbered link like `1.1 引言与样本空间` | None | Click → wait for video/page to load → detect completion → next |
| **章节测试 (Chapter Quiz)** | Link like `1.6 章节测试1` with badge | Number badge (task points) `1` | Extract questions → answer → submit → retry if needed |
| **课程思政/案例** | Link with special topic name | Number badge `2` | Click → read through → detect completion |

**Content sections** typically contain:
- **Video lessons** — play automatically, need to watch to trigger completion
- **Document pages** — read/scroll to mark complete
- **PPT slides** — flip through pages

**章节测试** are inline quizzes within chapters:
- Question types: 单选题 (single choice), 多选题 (multiple choice), 判断题 (true/false), 简答题 (essay)
- Usually **unlimited retries** (unlike 考试)
- Submit → view score → retry if < 100%
- Clicking into one reveals question count, types, and scoring

Expand each chapter by clicking the expand arrow (ref: generic with ``) and record all section types.

**Important**: The chapters page snapshot can be very large (30KB+). Use `--depth` flag or extract section data programmatically:

```powershell
playwright-cli.cmd -s=chaoxing-chrome run-code "async page => { const iframe = page.frames().find(f => f.url().includes('mooc2')); const links = await iframe.locator('a').all(); const sections = []; for (const l of links) { const t = await l.textContent(); if (t && /\d+\.\d+/.test(t)) sections.push(t.trim()); } return sections; }"
```

#### 2c. The "讨论" (Discussions) Tab

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <讨论-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

Discussion forums may require:
- Reading topics and posting replies
- Minimum word count for replies
- May count toward 任务点 progress

#### 2d. The "作业" (Assignments) Tab

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <作业-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

**Observed structure:**

- Filter bar: `全部` (All) / `已完成` (Completed) / `未完成` (Unfinished)
- Count display: `X/Y`
- Plagiarism notice: `提交的作业将经过大雅相似度分析系统，请勿抄袭`
- Each assignment shows: title, status (已完成/未完成/已过期), due date

**Assignment types:**
- **简答题 (Essay/Short Answer)** — text input, possibly with file upload
- **文件上传 (File Upload)** — requires uploading a document
- **互评 (Peer Review)** — requires reviewing other students' work

**CRITICAL**: Assignments go through 大雅 plagiarism check. Generated content must be original.

If `暂无作业` appears, this course has no standalone assignments.

#### 2e. The "考试" (Exams) Tab — HIGHEST RISK ⚠️

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <考试-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

**This is where the most dangerous constraints hide.** Exams have THREE possible states:

| State | Snapshot Text | Action |
|---|---|---|
| **待完成 (Pending)** | Active exam with entry button | MUST analyze constraints before entering |
| **已完成 (Completed)** | `已完成` label | Skip |
| **已过期 (Expired)** | `已过期` label | Cannot attempt |

For each pending exam, **click into it and inspect EVERY parameter BEFORE starting:**

- **题目数量** (Question count) — how many and what types
- **允许尝试次数** (Allowed attempts) — often only 1-3
- **答题限时** (Time limit) — e.g., `90 分钟`
- **截止时间** (Deadline) — when it expires
- **公布答案** (Publish answers) — usually hidden for exams
- Question composition — watch for **简答题 (essay)** which need full text generation

**Decision Framework for 考试:**

```
Is it a 考试?
├── Status: 已过期 → Cannot attempt, skip
├── Status: 已完成 → Skip
├── Status: 已完成 (but score < 60) → Check if retry allowed
└── Status: 待完成 (Pending) ⚠️ HIGH RISK
    ├── Check: 允许尝试次数
    │   ├── 1 attempt → MUST get it right first time
    │   └── 3+ attempts → Can learn from first attempt
    ├── Check: 答题限时
    │   ├── Has time limit → Need timer management
    │   └── No limit → Can work methodically
    ├── Check: Has 简答题? → Need full text generation
    ├── Check: 公布答案 → Usually NO for exams
    └── Strategy:
        ├── Extract ALL questions via snapshot FIRST
        ├── Send each to AI for answer generation
        ├── For 简答题: generate comprehensive text
        ├── Fill all answers before starting timer
        └── Submit only when user confirms
```

#### 2f. The "资料" (Materials) Tab

```powershell
playwright-cli.cmd -s=chaoxing-chrome click <资料-ref>
playwright-cli.cmd -s=chaoxing-chrome snapshot --boxes
```

Course reference materials — PDFs, documents, links. Usually not required for progress, but check for 任务点 badges.

### Phase 3: Classification & Strategy Matrix

After analyzing all courses, build this matrix:

```
Chaoxing Task Type         | Count | Auto Strategy
----------------------------|-------|------------------------------------------
章节-视频/文档              | N     | playwright open section → detect video end / page viewed → next
章节-章节测试(选择/判断)     | N     | Open quiz → extract questions → answer → submit → check score → retry if <100
章节-章节测试(含简答)        | N     | Same as above + generate essay answers
作业-简答题                  | N     | Read question → AI generate text → paste → submit
作业-文件上传                | N     | Download template → AI generate → upload
考试-测试(选择/判断) ⚠️      | N     | Extract questions FIRST → AI answer → fill → submit (mind attempts+timer)
考试-测试(含简答) ⚠️⚠️       | N     | Same + generate essays — DOUBLE CHECK constraints before starting
讨论                         | N     | Read topic → AI generate reply → post
课程思政/案例                | N     | Click → read → detect completion
```

### Phase 4: Edge Case Catalog

Document every deviation:

1. **No 任务点进度 indicator**: Many courses don't show the overlay on the card. These either have no tasks assigned or use a different evaluation. Must check the 章节 tab to confirm.
2. **章节测试 with 简答题**: Unlike pure choice quizzes, these require text input. Some may require teacher grading.
3. **考试 with 1 attempt + timer**: The most dangerous combination. Must be fully prepared before clicking "开始".
4. **已过期 考试**: Cannot be attempted — automatically excluded from automation.
5. **Empty tabs**: `暂无任务`, `暂无作业`, `暂无考试` are common. Don't waste time on empty tabs.
6. **课程已结束**: Ended courses appear after active ones. Usually not possible to complete.
7. **Duplicate course names**: Same course may appear for different classes (e.g., 计算机体系结构与嵌入式系统原理 ×2). Must check courseid/clazzid.
8. **iframe navigation**: Course content is in an iframe. All interactions must target the correct iframe frame.
9. **章节 expand/collapse**: Chapters are collapsed by default. Must click expand arrows to see subsections.
10. **Plagiarism detection (大雅相似度)**: All 作业 submissions go through plagiarism check. AI-generated text must be sufficiently modified.

## Observed Course Analysis (2026-06-21)

### 概率论与数理统计 (鲜思东) — 79/100 任务点

**章节 tab**: 8+ chapters, each with 5-8 subsections including:
- Content sections (e.g., "1.1 引言与样本空间", "2.3 分布函数")
- 章节测试 (e.g., "1.6 章节测试1" with 1 task point, "2.7 第二章测试2" with 1 task point)
- 课程思政/案例 (e.g., "1.8 课程思政/教学应用案例" with 2 task points)
- 21 missing task points need automation

**作业 tab**: `暂无作业` (0/0) — no standalone assignments

**考试 tab**: 3 exams:
- 第二次阶段测试补测 — `已过期` (skip)
- 第二次阶段测试（第4-7章）-副本 — `已完成` (skip)
- 第一次章节测试（1-2章） — `已完成` (skip)

**任务 tab**: `暂无任务` (empty)

## Output: Automation Design Document

After completing all phases, produce:

1. **Course Inventory Table** — all courses with 任务点进度, tab status summary, and assigned strategy
2. **Task Type Catalog** — every distinct task type found across all courses, with snapshot examples
3. **Strategy Matrix** — which automation approach for which task type
4. **Risk Assessment** — tasks ranked by risk:

```
RISK LEVEL    | TASK TYPE
--------------|------------------------------------------
CRITICAL ⚠️⚠️  | 考试-测试 with 1 attempt + timer + 简答题
HIGH ⚠️       | 考试-测试 with limited attempts
MEDIUM        | 章节测试 with 简答题, 作业-文件上传
LOW           | 章节-视频/文档, 讨论, 课程思政
```

5. **Script Architecture** — recommended file structure
6. **Execution Order** — process low-risk content sections first, tackle 考试 last

## Script Architecture Template

```
scripts/
├── chaoxing_config.json       # Course list, URLs, task point targets
├── chaoxing_orchestrator.ah2  # AHK v2 main controller
├── chapter_content_bot.py     # Navigate 章节 tree, play videos, detect completion
├── chapter_quiz_solver.py     # Open 章节测试 → extract questions → solve → retry
├── exam_solver.py             # HIGH-RISK: analyze constraints → extract → solve → submit
├── assignment_builder.py      # Download assignment templates → AI generate → submit
├── discussion_bot.py          # Read discussion topics → generate replies → post
├── course_analyzer.py         # Snapshot parser, 任务点 classifier, progress tracker
└── output/                    # Generated assignment files
```

Python tools use conda base environment. The AHK script serves as the top-level orchestrator, calling Python scripts and playwright-cli commands in sequence.

## Common Pitfalls

1. **Assuming all courses have the same structure**: Each Chaoxing course is independently configured. Some have only 章节, others have 作业 + 考试. Must check every tab.
2. **Missing the iframe**: Course content is rendered inside an iframe (`mooc2-ans.chaoxing.com`). Direct page selectors won't work — must use `page.frames().find(...)` for run-code or rely on snapshot refs.
3. **Not expanding 章节**: Chapters are collapsed. Click expand arrows (``) or the chapter header to reveal subsections.
4. **Overlooking 考试 constraints**: The deadliest mistake. Always check 允许尝试次数 and 答题限时 before clicking start.
5. **Snapshot size**: 章节 pages can produce 30KB+ snapshots. Use programmatic extraction (`run-code`) for large pages.
6. **Ref staleness**: After tab switching, always take a fresh snapshot before using refs.
7. **课程已结束 courses**: These appear after active courses on the same page. Usually cannot be completed (past semester).
8. **PowerShell URL escaping**: Chaoxing URLs have `&` — use `--%` in PowerShell.
