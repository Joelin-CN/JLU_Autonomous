"""
Chapter tree navigation for content completion and quiz solving.

Provides functions for navigating within a course: opening the chapter tab,
returning to the chapter tree after completing a section, extracting the
chapter directory tree, and clicking individual sections.

Used by BOTH the quiz solver and the content bot.
"""

import time
import json
import re
from typing import Optional

from ...constants import SCRIPT_DIR, TMP_DIR
from ...logging_setup import log
from ...browser.engine import pw_run_code
from ...browser.js_runner import pw_extract_result
from ...platform.navigation import pw_goto_course
from ...utils import human_delay


# ── Snapshot Helpers ──────────────────────────────────────────────
# Canonical implementations live in chaoxing.utils; re-exported here
# for backward compatibility with existing callers.
from ...utils import find_ref_by_text, parse_progress_from_snapshot  # noqa: F401


# ── Navigation Functions ──────────────────────────────────────────

def _click_chapter_tab() -> str:
    """Click the 章节 tab to load the chapter-tree iframe.

    Uses the SAME strategy as platform.scanner.scan_course_sections, which is
    the proven-working path: match an <a> whose exact text is "章节" and click
    it, falling back to Playwright's getByRole('link', {name:'章节'}).

    The previous approach (find_ref_by_text on a pw_snapshot ref + pw_click)
    clicked the wrong element and never loaded the chapter-tree iframe
    (.../mycourse/studentcourse), so every subsequent navigate_to_section saw
    'no-iframe'. Empirically, find_ref_by_text+pw_click → tree iframe NONE,
    while getByRole click → iframe loads (clicktitle=65). See handoff.

    Returns the click result string ('clicked' / 'clicked-via-role' /
    'not-found' / 'err:...').
    """
    js = r"""
    async (page) => {
        const links = await page.locator('a').all();
        for (const link of links) {
            const text = (await link.textContent() || '').trim();
            if (text === '章节') {
                await link.click();
                await page.waitForTimeout(2500 + Math.floor(Math.random() * 1200));
                return 'clicked';
            }
        }
        try {
            await page.getByRole('link', { name: '章节' }).click();
            await page.waitForTimeout(2500 + Math.floor(Math.random() * 1200));
            return 'clicked-via-role';
        } catch (e) {
            return 'not-found';
        }
    }
    """
    try:
        result = pw_extract_result(pw_run_code(js))
    except Exception as e:
        result = f"err:{e}"
    return str(result)


def open_course_chapters(courseid: str, clazzid: str, cpi: str, name: str = None):
    """Open course and navigate to 章节 tab (full reload — use once only).

    Navigates to the course page via stucoursemiddle, then clicks
    the 章节 tab to show the full chapter tree.

    Args:
        courseid: Course ID from course card.
        clazzid: Class ID from course card.
        cpi: Course plan identifier (default "415409200").
        name: Optional course name for logging.
    """
    if name:
        log(f"Opening course: {name}")
    pw_goto_course(courseid, clazzid, cpi)
    human_delay(3.0, 0.25)

    result = _click_chapter_tab()
    if result == "not-found":
        log("Could not find 章节 tab!", "ERROR")
    human_delay(2.0, 0.25)


def go_back_to_chapter_tree(courseid: str, clazzid: str, cpi: str) -> bool:
    """Navigate back to the chapter tree after completing a section.

    Three strategies, tried in order:
    1. If main page is on studentstudy (mooc1), use page.goto() to
       the course URL via pw_goto_course(), then click 章节 tab.
    2. If still on the course page, click 章节 tab then use
       lightweight iframe.goto() to refresh the chapter tree.
    3. (Caller should fall back to open_course_chapters() on failure.)

    Args:
        courseid: Course ID.
        clazzid: Class ID.
        cpi: Course plan identifier.

    Returns:
        True if the chapter tree was successfully refreshed.
    """
    # Check where we are
    js_url = "async (page) => page.url()"
    raw = pw_run_code(js_url)
    current_url = pw_extract_result(raw)
    log(f"    Current URL: {current_url[:100]}")

    if "studentstudy" in current_url or "mooc1.chaoxing.com" in current_url:
        # Main page is on studentstudy — navigate directly to course page
        log("    On studentstudy, navigating to course page...")
        pw_goto_course(courseid, clazzid, cpi)
        human_delay(3.0, 0.25)

        # Click 章节 tab (default view is 任务) — proven click strategy
        _click_chapter_tab()
        return True

    # Normal case: still on course page — ensure 章节 tab is active and the
    # chapter-tree iframe is (re)loaded. _click_chapter_tab is what actually
    # brings up the .../studentcourse iframe; the lightweight iframe.goto below
    # is a secondary refresh that now finds it.
    _click_chapter_tab()

    # Use lightweight iframe.goto() to refresh chapter tree
    chapter_url = (
        "https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse"
        f"?courseid={courseid}&clazzid={clazzid}"
        f"&cpi={cpi}&pageHeader=0"
    )
    js_goto = (
        "async (page) => {"
        " const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));"
        f" if (iframe) {{ await iframe.goto('{chapter_url}'); return 'goto-ok'; }}"
        " return 'no-iframe'; }"
    )
    raw = pw_run_code(js_goto)
    result = pw_extract_result(raw)
    human_delay(3.0, 0.25)
    log(f"    iframe.goto result: {result}")
    return result == "goto-ok"


def get_chapter_tree() -> list:
    """Extract the chapter directory tree from the current page.

    Scans the mooc2-ans iframe for chapter headers (emphasis elements
    with numbers) and their associated section links.

    Returns:
        List of dicts: [{"chapter": "第1章", "sections": ["1.1 标题", ...]}, ...]
        Returns empty list on failure.
    """
    js = """
    async (page) => {
        const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
        if (!iframe) return JSON.stringify({error: 'no-iframe'});

        const chapters = [];
        // Find all chapter headers (emphasis elements with numbers)
        const emphasisEls = await iframe.locator('emphasis').all();

        for (const emph of emphasisEls) {
            const chNum = await emph.textContent();
            // Get parent chapter container
            const parent = await emph.evaluateHandle(el => el.closest('[class*="chapter"]') || el.closest('generic'));

            // Find section links within this chapter
            const links = await parent.locator('a').all();
            const sections = [];
            for (const link of links) {
                const text = await link.textContent();
                if (text && /\\d+\\.\\d+/.test(text)) {
                    sections.push(text.trim());
                }
            }

            if (sections.length > 0) {
                chapters.push({chapter: chNum.trim(), sections});
            }
        }

        return JSON.stringify(chapters);
    }
    """
    raw = pw_run_code(js)
    parsed = pw_extract_result(raw)
    # pw_extract_result already JSON-decodes the playwright result envelope.
    # The JS returns JSON.stringify(chapters), so parsed is typically a JSON
    # string still needing one more decode; tolerate an already-decoded list.
    if isinstance(parsed, list):
        return parsed
    try:
        return json.loads(parsed)
    except (json.JSONDecodeError, TypeError):
        log(f"  Failed to parse chapter tree: {str(parsed)[:100]}", "WARN")
        return []


def navigate_to_section(chapter_num: int, section_num: int) -> bool:
    """Click a specific section in the chapter tree to open it.

    Searches for a link whose text starts with the section identifier
    (e.g. "1.3") and clicks it within the mooc2-ans iframe.

    Args:
        chapter_num: Chapter number (1-indexed).
        section_num: Section number within the chapter (1-indexed).

    Returns:
        True if the section was found and clicked.
    """
    section_id = f"{chapter_num}.{section_num}"
    log(f"  Navigating to {section_id}...")

    js = f"""
    async (page) => {{
        const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
        if (!iframe) return 'no-iframe';

        const links = await iframe.locator('a').all();
        for (const link of links) {{
            const text = await link.textContent();
            if (text && text.trim().startsWith('{section_id}')) {{
                await link.click();
                await page.waitForTimeout(800 + Math.floor(Math.random() * 400));
                return 'clicked:' + text.trim();
            }}
        }}
        return 'not-found';
    }}
    """
    result = pw_extract_result(pw_run_code(js))
    log(f"    Navigate result: {result}")
    return str(result).startswith("clicked:")
