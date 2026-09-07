"""
Test script: Verify question positioning logic in quiz solver.
Opens account 0, navigates to 概率论与数理统计, opens a quiz section,
and validates that question boundary detection works correctly.
"""
import sys
import time
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    load_config, cfg, log, set_active_session,
    pw, pw_snapshot, pw_click, pw_goto, pw_goto_course,
    pw_run_code, pw_run_code_file, pw_extract_result,
    find_ref_by_text, parse_progress_from_snapshot,
    chaoxing_login, ensure_chaoxing_viewport,
    read_all_chaoxing_credentials,
)


def test_login():
    """Step 1: Login as account 0."""
    log("=" * 60)
    log("STEP 1: Login as account 0")
    log("=" * 60)

    set_active_session("chaoxing-chrome")

    snap = pw_snapshot()
    log(f"Current page title check...")

    # Check if already logged in by various indicators
    logged_in_indicators = [
        "个人空间", "i.chaoxing.com/base", "i.mooc.chaoxing.com/space",
        "重庆邮电大学", "我学的课",
    ]
    for indicator in logged_in_indicators:
        if indicator in snap:
            log(f"Already logged in! (found '{indicator}')", "OK")
            # Navigate to base to ensure consistent state
            pw_goto("https://i.chaoxing.com/base")
            time.sleep(2)
            return True

    # Check URL via JS
    js_url = "async (page) => page.url()"
    raw = pw_run_code(js_url)
    current_url = pw_extract_result(raw)
    log(f"Current URL: {current_url}")
    if "i.chaoxing.com" in current_url or "i.mooc.chaoxing.com" in current_url:
        log("Already logged in! (by URL)", "OK")
        pw_goto("https://i.chaoxing.com/base")
        time.sleep(2)
        return True

    if "用户登录" in snap:
        log("On login page, attempting login...")
        result = chaoxing_login(0)
        # Even if JS returns not-ok, check if we actually got in
        snap2 = pw_snapshot()
        if "个人空间" in snap2 or "i.chaoxing.com" in snap2:
            log("Login succeeded despite JS result", "OK")
            return True
        if result:
            log("Login SUCCESS", "OK")
            return True
        else:
            log("Login FAILED", "ERROR")
            return False

    log(f"Unexpected page state: {snap[:300]}", "WARN")
    # Last resort: try navigating to base
    pw_goto("https://i.chaoxing.com/base")
    time.sleep(3)
    snap2 = pw_snapshot()
    if "个人空间" in snap2:
        return True
    return False


def test_navigate_to_course():
    """Step 2: Navigate to 概率论与数理统计 and click 章节."""
    log("\n" + "=" * 60)
    log("STEP 2: Navigate to course → 章节")
    log("=" * 60)

    courseid = "255106367"
    clazzid = "127207872"
    cpi = "415409200"

    pw_goto_course(courseid, clazzid, cpi)
    time.sleep(3)

    # Click 章节 via JS
    js_click = """
    async (page) => {
        const links = await page.locator('a').all();
        for (const link of links) {
            const text = (await link.textContent() || '').trim();
            if (text === '章节') {
                await link.click();
                await page.waitForTimeout(3000);
                return 'clicked';
            }
        }
        try {
            await page.getByRole('link', { name: '章节' }).click();
            await page.waitForTimeout(3000);
            return 'clicked-via-role';
        } catch(e) {
            return 'not-found';
        }
    }
    """
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(Path(__file__).parent), encoding='utf-8')
    tmp.write(js_click)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=15)
        result = pw_extract_result(raw)
        log(f"Click 章节 result: {result}")
    finally:
        try: os.unlink(tmp.name)
        except: pass

    time.sleep(2)
    snap = pw_snapshot()
    log(f"[Snapshot] Page URL check: {'mooc2-ans' in snap}")
    return True


def test_navigate_to_quiz():
    """Step 3: Navigate to '1.6 章节测试1' in the chapter tree."""
    log("\n" + "=" * 60)
    log("STEP 3: Navigate to quiz section 1.6 章节测试1")
    log("=" * 60)

    section_num = "1.6"
    js = f"""
    async (page) => {{
        const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
        if (!iframe) return 'no-iframe';
        const links = await iframe.locator('a').all();
        for (const link of links) {{
            const text = await link.textContent();
            if (text && text.includes('{section_num}')) {{
                await link.click();
                return 'clicked:' + text.trim();
            }}
        }}
        return 'not-found';
    }}
    """
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(Path(__file__).parent), encoding='utf-8')
    tmp.write(js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=20)
        result = pw_extract_result(raw)
        log(f"Navigate to {section_num}: {result}")
        if not result.startswith("clicked:"):
            log("Failed to navigate to quiz section!", "ERROR")
            return False
    finally:
        try: os.unlink(tmp.name)
        except: pass

    time.sleep(3)
    return True


def test_find_question_boundaries():
    """Step 4: Find question boundaries using .newZy_TItle / .Zy_TItle elements."""
    log("\n" + "=" * 60)
    log("STEP 4: Detect question boundaries in quiz iframe")
    log("=" * 60)

    # Ensure viewport is large enough
    ensure_chaoxing_viewport(2048, 1152)

    find_js = r"""
    async (page) => {
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({error: 'no-iframe'});

        let titleBoxes = [];
        let usedIframe = '';
        let contentBottom = 0;

        for (const iframe of candidates) {
            const urlShort = iframe.url().substring(0, 100);

            // Find 题号 elements (.newZy_TItle or .Zy_TItle)
            try {
                const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
                const titleCount = await titleEls.count();
                if (titleCount >= 1) {
                    for (let i = 0; i < titleCount; i++) {
                        try {
                            const box = await titleEls.nth(i).boundingBox();
                            if (box && box.width > 30 && box.height > 10) {
                                // Also get the text content of the 题号
                                const text = (await titleEls.nth(i).textContent() || '').trim();
                                titleBoxes.push({
                                    y: Math.round(box.y),
                                    h: Math.round(box.height),
                                    x: Math.round(box.x),
                                    w: Math.round(box.width),
                                    text: text,
                                });
                            }
                        } catch(e) {}
                    }
                    if (titleBoxes.length > 0) {
                        usedIframe = urlShort;
                    }
                }
            } catch(e) {}

            // Also get the last content element's bottom for end boundary of last Q
            try {
                const bottomEls = iframe.locator('.Zy_ulTop, .TiMu, .newTiMu');
                const bottomCount = await bottomEls.count();
                if (bottomCount > 0) {
                    const lastBox = await bottomEls.nth(bottomCount - 1).boundingBox();
                    if (lastBox) {
                        contentBottom = Math.round(lastBox.y + lastBox.height);
                    }
                }
            } catch(e) {}

            if (titleBoxes.length > 0) break;
        }

        // Fallback: no 题号 elements
        if (titleBoxes.length === 0) {
            for (const iframe of candidates) {
                for (const sel of ['.Zy_ulTop', '.TiMu', '.newTiMu', '.questionDiv']) {
                    try {
                        const els = iframe.locator(sel);
                        const c = await els.count();
                        if (c >= 1) {
                            for (let i = 0; i < c; i++) {
                                const box = await els.nth(i).boundingBox();
                                if (box && box.width > 100 && box.height > 30) {
                                    const text = (await els.nth(i).textContent() || '').trim();
                                    titleBoxes.push({
                                        y: Math.round(box.y), h: Math.round(box.height),
                                        x: Math.round(box.x), w: Math.round(box.width),
                                        text: text.substring(0, 80),
                                    });
                                }
                            }
                            if (titleBoxes.length > 0) {
                                usedIframe = iframe.url().substring(0, 100);
                                break;
                            }
                        }
                    } catch(e) {}
                }
                if (titleBoxes.length > 0) break;
            }
        }

        if (titleBoxes.length === 0) return JSON.stringify({error: 'no-questions-found'});

        // Sort top-to-bottom and deduplicate by Y position
        titleBoxes.sort((a, b) => a.y - b.y);
        let merged = [];
        for (const tb of titleBoxes) {
            const last = merged[merged.length - 1];
            if (last && Math.abs(tb.y - last.y) <= 10) {
                if (tb.y < last.y) { last.y = tb.y; last.x = tb.x; last.w = tb.w; last.h = tb.h; }
                // Keep both texts
                if (tb.text && !last.text) last.text = tb.text;
            } else {
                merged.push({...tb});
            }
        }
        titleBoxes = merged;

        // Build question boundaries
        let questions = [];
        for (let i = 0; i < titleBoxes.length; i++) {
            const startY = titleBoxes[i].y;
            let endY;
            if (i + 1 < titleBoxes.length) {
                endY = titleBoxes[i + 1].y - 4;
            } else {
                endY = Math.max(startY + 200, contentBottom + 12);
            }
            questions.push({
                index: i + 1,
                startY: startY,
                endY: endY,
                titleH: titleBoxes[i].h,
                titleText: titleBoxes[i].text || '',
            });
        }

        return JSON.stringify({
            ok: true,
            count: questions.length,
            iframe: usedIframe,
            contentBottom: contentBottom,
            questions: questions,
        });
    }
    """
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(Path(__file__).parent), encoding='utf-8')
    tmp.write(find_js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=25)
        result_str = pw_extract_result(raw)
        result = json.loads(result_str)
    finally:
        try: os.unlink(tmp.name)
        except: pass

    if not result.get("ok"):
        log(f"Failed to find questions: {result.get('error', 'unknown')}", "ERROR")
        return None

    log(f"Found {result['count']} question boundaries:", "OK")
    log(f"  Iframe: {result.get('iframe', '?')}")
    log(f"  Content bottom: {result.get('contentBottom', 0)}")
    for q in result['questions']:
        height = q['endY'] - q['startY']
        log(f"  Q{q['index']}: Y={q['startY']}..{q['endY']} (height={height}px)"
            f"  titleText='{q.get('titleText', '')[:60]}'")

    return result


def test_snapshot_question_text():
    """Step 5: Get snapshot and show how questions appear in text."""
    log("\n" + "=" * 60)
    log("STEP 5: Snapshot-based question text extraction")
    log("=" * 60)

    snap = pw_snapshot()

    # Look for question-related text patterns
    lines = snap.split("\n")
    quiz_lines = []
    for line in lines:
        stripped = line.strip()
        if any(kw in stripped for kw in [
            "单选", "多选", "判断", "简答", "填空",
            "第", "题", "A.", "B.", "C.", "D.",
            "newZy_TItle", "Zy_TItle", "TiMu",
        ]):
            quiz_lines.append(stripped)

    log(f"Found {len(quiz_lines)} quiz-related lines in snapshot:")
    for i, line in enumerate(quiz_lines[:40]):
        log(f"  [{i}] {line[:120]}")

    # Test the _click_option question boundary logic
    log("\n--- Testing question boundary regex matching ---")
    # Simulate finding question 1 boundaries
    q_index = 1
    q_markers = [
        f"{q_index}.", f"第{q_index}题", f"{q_index}、",
        f"{q_index})", f"({q_index})", f"[{q_index}]",
        f"{q_index} ",
    ]

    start_line = None
    end_line = None
    for i, line in enumerate(lines):
        if start_line is None:
            for marker in q_markers:
                if marker in line:
                    start_line = i
                    log(f"  Q{q_index} START found at line {i}: {line.strip()[:100]}")
                    break
        elif end_line is None:
            for marker in [f"{q_index + 1}.", f"第{q_index + 1}题",
                           f"{q_index + 1}、", f"{q_index + 1})",
                           f"({q_index + 1})", f"[{q_index + 1}]"]:
                if marker in line:
                    end_line = i
                    log(f"  Q{q_index} END found at line {i}: {line.strip()[:100]}")
                    break

    if start_line is not None:
        if end_line is None:
            end_line = min(start_line + 50, len(lines))
        log(f"\n  Q{q_index} scope: lines {start_line}..{end_line} ({end_line - start_line} lines)")
        scope = "\n".join(lines[start_line:end_line])
        log(f"  Scope preview:\n{scope[:500]}")
    else:
        log(f"  Could not find Q{q_index} start marker!", "WARN")
        # Try broader pattern
        log("  Trying broader patterns...")
        for i, line in enumerate(lines[:100]):
            if '1' in line and any(c in line for c in ['.', '、', ')', '题']):
                log(f"    Line {i}: {line.strip()[:120]}")

    return snap


def test_option_click_simulation(snap):
    """Step 6: Simulate the option click logic without actually clicking."""
    log("\n" + "=" * 60)
    log("STEP 6: Test option-finding logic (dry-run, no clicks)")
    log("=" * 60)

    lines = snap.split("\n")

    # Test finding answer options for Q1
    for q_index in [1, 2, 3]:
        q_markers = [
            f"{q_index}.", f"第{q_index}题", f"{q_index}、",
            f"{q_index})", f"({q_index})", f"[{q_index}]",
            f"{q_index} ",
        ]

        start_line = None
        end_line = None
        for i, line in enumerate(lines):
            if start_line is None:
                for marker in q_markers:
                    if marker in line:
                        start_line = i
                        break
            elif end_line is None:
                for marker in [f"{q_index + 1}.", f"第{q_index + 1}题",
                               f"{q_index + 1}、", f"{q_index + 1})",
                               f"({q_index + 1})", f"[{q_index + 1}]"]:
                    if marker in line:
                        end_line = i
                        break

        if start_line is not None:
            if end_line is None:
                end_line = len(lines)
            scope = "\n".join(lines[start_line:end_line])

            # Search for option letters (A/B/C/D) in scope
            option_refs = {}
            for letter in ['A', 'B', 'C', 'D']:
                for pat in [f"{letter}.", f"{letter}、", f"{letter})", f"{letter} "]:
                    ref = find_ref_by_text(scope, pat)
                    if ref:
                        option_refs[letter] = ref
                        break

            log(f"  Q{q_index} (lines {start_line}..{end_line}): "
                f"options found: {list(option_refs.keys())}")
        else:
            log(f"  Q{q_index}: boundary NOT found", "WARN")


def main():
    log("=" * 60)
    log("QUESTION POSITIONING TEST")
    log("Account: 0 (13200003918)")
    log("Course: 概率论与数理统计 (id=255106367)")
    log("Target quiz: 1.6 章节测试1")
    log("=" * 60)

    set_active_session("chaoxing-chrome")

    # Step 1: Login
    if not test_login():
        log("Cannot proceed without login", "ERROR")
        return

    # Step 2: Navigate to course
    test_navigate_to_course()

    # Step 3: Navigate to quiz
    if not test_navigate_to_quiz():
        log("Cannot proceed without quiz page", "ERROR")
        return

    # Step 4: Find question boundaries (DOM-based)
    q_result = test_find_question_boundaries()

    # Step 5: Snapshot text analysis
    snap = test_snapshot_question_text()

    # Step 6: Test option finding
    test_option_click_simulation(snap)

    # Summary
    log("\n" + "=" * 60)
    log("TEST COMPLETE")
    if q_result:
        log(f"DOM detection: {q_result['count']} questions found", "OK")
        log(f"Question spacing (gaps between consecutive Qs):")
        qs = q_result['questions']
        for i in range(len(qs) - 1):
            gap = qs[i+1]['startY'] - qs[i]['endY']
            log(f"  Q{qs[i]['index']}→Q{qs[i+1]['index']}: "
                f"end={qs[i]['endY']} next_start={qs[i+1]['startY']} gap={gap}px")
    log("=" * 60)


if __name__ == "__main__":
    main()
