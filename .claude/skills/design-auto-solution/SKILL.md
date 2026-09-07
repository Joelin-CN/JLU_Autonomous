---
name: design-auto-solution
description: Design an automation solution for completing unfinished OUCHN LMS courses. Use when Codex has found unfinished courses via find-undo-course and needs to analyze course page structures, classify task types, identify special cases, and design a concrete automation script strategy before writing any code.
---

# Design Auto Solution for OUCHN Course Completion

## Overview

After `sign-in-ouchn` and `find-undo-course` have identified courses with progress below 100%, this skill guides the systematic analysis of every unfinished course's internal page structure. The goal is to produce a complete task-type classification and an automation strategy matrix before writing a single line of automation script.

**Critical principle**: Do NOT assume all courses have the same structure. Each course must be opened and its 形考任务 (formative) and 终考任务 (summative) tabs must be inspected individually. Hidden task subtypes can drastically change the automation approach.

## Required Setup

- `sign-in-ouchn` must have completed successfully (persistent session `-s=ouchn-chrome` is open and logged in).
- `find-undo-course` must have produced a list of courses with progress < 100%.
- Use `playwright-cli` from the workspace root for all browser interactions.
- Run commands from the workspace root. Single `playwright-cli.cmd` actions per shell command.

## Workflow

### Phase 1: Portal-Level Discovery

1. From the portal homepage (`https://menhu.pt.ouchn.cn/site/ouchnPc/index`), take a boxed snapshot:

```powershell
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

2. For each course card in `我的课程`, record:
   - Course name and code
   - Learning progress percentage
   - 形考作业 status (e.g. `3/4`)
   - 终考作业 status (e.g. `0/1`)
   - The `去学习` link URL (contains course ID)

3. Handle pagination. The portal may split courses across multiple pages. Click page numbers using refs from the latest snapshot.

4. Build the initial course inventory. Filter out courses at 100%.

### Phase 2: Per-Course Deep Analysis

For **every** unfinished course, open it in a new tab and inspect two dimensions:

#### 2a. The "全部" (All) Tab — Video & Reference Content

Navigate to the course main page and click `未完成` (unfinished) checkbox to filter:

```powershell
playwright-cli.cmd -s=ouchn-chrome goto "https://lms.ouchn.cn/course/{courseId}/ng#/"
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
# Find the 未完成 checkbox ref, then:
playwright-cli.cmd -s=ouchn-chrome check <checkbox-ref>
```

The filtered view reveals which section types have unfinished items:
- **音视频教材** (video/audio materials) — identified by icon `` and `影片长度` label
- **参考资料** (reference materials) — icon ``, has `查看文件` button
- **页面** (pages) — icon ``
- **线上链接** (online links) — icon ``
- **讨论** (discussions) — icon ``
- **课堂直播** (live classes) — icon ``, typically all `已结束`

Video items display `影片长度` (duration) like `00:14:44` — record these for time estimation.

#### 2b. The "形考任务" (Formative Assessment) Tab

```powershell
playwright-cli.cmd -s=ouchn-chrome goto "https://lms.ouchn.cn/course/{courseId}/ng#/formal-exam"
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

Formative tasks come in TWO subtypes:

| Subtype | Snapshot Signature | Key Parameters |
|---------|-------------------|----------------|
| **测试 (Test)** | icon ``, shows `题目数量`, `总分数`, `测试截止时间` | 999 attempts, highest score, auto-graded |
| **作业 (Assignment)** | icon ``, shows `作业交付截止` | File upload, teacher-graded |

For test-type, click into one to inspect:
- Question types: 单选题 (radio), 多选题 (checkbox), 判断题 (radio)
- Question pool size vs. selected count
- Score per question
- Whether `公布答案` (publish answers) is enabled

**Important**: Even if all 形考 show as completed (e.g. `4/4`), still open the tab to confirm. The portal count may include assignment-type tasks that are actually incomplete.

#### 2c. The "终考任务" (Summative Assessment) Tab

```powershell
playwright-cli.cmd -s=ouchn-chrome goto "https://lms.ouchn.cn/course/{courseId}/ng#/final-exam"
playwright-cli.cmd -s=ouchn-chrome snapshot --boxes
```

**This is where the most dangerous surprises hide.** Summative tasks have THREE possible subtypes:

| Subtype | Snapshot Signature | Critical Constraints |
|---------|-------------------|---------------------|
| **测试 (Test)** ⚠️ | icon ``, `题目数量`, `允许尝试次数` | **Limited attempts (e.g. 3)**, **time limit (e.g. 90 min)**, may include **简答题 (essay)** |
| **作业 (Assignment)** | icon ``, `作业交付截止` | Teacher-graded, file upload |
| **暂无终考任务** | text `暂无终考任务` | Nothing to do |

**CRITICAL**: For 终考-测试型, click in and inspect EVERY parameter:
- `允许尝试次数` — often only 1-3, NOT 999
- `答题限时` — time limit in minutes (if present)
- `公布成绩` — may say `不公布` (not published)
- `公布答案` — almost always `不公布答案`
- Question composition — look for **简答题 (essay/short-answer)** which require text input, not just clicking

Example from 临床医学概论:
```
测试试题：目前测试中共有30道单选题，10道判断题，2道简答题
允许尝试次数: 3
答题限时: 90 分钟
公布成绩: 不公布
公布答案: 不公布答案
```

### Phase 3: Classification & Strategy Matrix

After analyzing all courses, build this matrix:

```
Task Type              | Count | Auto Strategy
-----------------------|-------|------------------------------------------
视频/音频教材           | N     | playwright click → detect playback end → next
参考资料               | N     | playwright click 查看文件 → wait → close/back
形考-测试(选择/判断)     | N     | Submit blank first → extract [checked] answers → redo to 100
形考-作业(文件上传)      | N     | Download template → AI generate → upload
终考-测试(含简答) ⚠️     | N     | DeepSeek per-question (essay needs full text generation)
终考-作业(文件上传)      | N     | Download → AI generate → upload (DO NOT auto-submit)
讨论                   | N     | DeepSeek generate reply → fill → post
```

### Phase 4: Edge Case Catalog

Document every deviation from the "typical" pattern:

1. **终考伪装成测试**: 临床医学概论 has a 终考 that is a test (not assignment), with essay questions and a 90-minute timer. This is the highest-risk task type.
2. **形考作业混在形考统计中**: 计算机应用基础 shows `3/4` but the 4th item is an assignment-type `学习过程表现`, not a test.
3. **终考无任务**: 社会心理适应 and 常见疾病与预防 have a 终考 tab but display `暂无终考任务`.
4. **门户进度≠课程页进度**: Portal may show slightly stale progress (e.g. 83.1% vs 82.4% on course page).
5. **不公布答案的终考**: Unlike 形考 where you can submit and see correct answers, 终考-测试型 typically hides answers — making the first attempt blind.

## Decision Framework for 终考 (Summative Assessment)

This is the highest-stakes decision because 终考 often has severe constraints:

```
Is it a 终考?
├── Type: 暂无终考任务 → Skip, no action needed
├── Type: 作业 (Assignment)
│   └── Strategy: Download → AI-generate content → upload
│   └── ⚠️ NEVER auto-submit without user review
└── Type: 测试 (Test) ⚠️ HIGH RISK
    ├── Check: 允许尝试次数 (if 1 → MUST get right first time)
    ├── Check: 答题限时 (if present → need time management)
    ├── Check: Has 简答题? → DeepSeek must generate full text
    ├── Check: 公布答案? (almost always NO for 终考)
    └── Strategy: 
        ├── Extract ALL questions via snapshot first
        ├── Send each question to DeepSeek for answer
        ├── For 简答题: generate comprehensive essay responses
        ├── Fill all answers BEFORE starting the timer
        └── Submit only when user confirms
```

## Common Pitfalls Encountered

1. **Assuming all courses have the same structure**: Each course is independently configured. Must check every tab of every course.
2. **Trusting portal summary numbers**: `形考 3/4` doesn't mean 3 tests done + 1 test remaining. The 4th could be an assignment.
3. **Overlooking 终考-测试型**: The most dangerous type. Looks like a regular test but has severe constraints (few attempts, time limit, essay questions, hidden answers).
4. **Snapshot size**: Course pages with many items produce very large snapshots (70KB+). Use `--depth` flag or eval for targeted extraction when needed.
5. **Ref staleness**: After tab switching, mode changes, or navigation, always take a fresh snapshot before using refs.
6. **PowerShell URL escaping**: URLs with `&` need `--%` in PowerShell. Use `goto` with already-navigated pages when possible.
7. **Tab management**: With 6+ tabs open, use `tab-select` by index before `goto` to avoid navigating the wrong tab.

## Output: Automation Design Document

After completing all phases, produce a design document covering:

1. **Course Inventory Table** — all courses with progress, task breakdown, and assigned strategy
2. **Task Type Catalog** — every distinct task type found, with snapshot examples
3. **Strategy Matrix** — which automation approach for which task type
4. **Risk Assessment** — tasks ranked by risk (终考-测试-简答 > 终考-测试 > 终考-作业 > 形考-测试 > 视频)
5. **Script Architecture** — recommended file structure under `scripts/`
6. **Execution Order** — which courses to automate first (start with low-risk video courses, tackle high-risk 终考 last)

## Script Architecture Template

```
scripts/
├── config.json           # Course list, URLs, progress targets
├── ouchn_auto.ah2        # AHK v2 main controller (flow orchestration)
├── video_watcher.py      # Auto-play videos, detect completion
├── quiz_solver.py         # Extract questions → DeepSeek → fill answers
├── assignment_builder.py  # Download templates → AI generate → package
├── page_analyzer.py       # Snapshot parser, task type classifier
└── output/                # Generated assignment files for upload
```

Python tools use conda base environment. The AHK script serves as the top-level orchestrator, calling Python scripts and playwright-cli commands in sequence.
